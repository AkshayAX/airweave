"""DeepSeek-OCR converter for images and scanned documents.

Local OCR using DeepSeek-OCR model with GPU acceleration support.
Replaces Mistral API for air-gapped deployment.
"""

import asyncio
import os
import tempfile
from typing import Dict, List
import logging
from PIL import Image

from .base import BaseTextConverter

logger = logging.getLogger(__name__)


class DeepSeekOCRConverter(BaseTextConverter):
    """Converts images and scanned PDFs using local DeepSeek-OCR model.

    Supported formats:
    - Images: JPG, JPEG, PNG, BMP, TIFF
    - PDFs: Scanned PDFs (converts pages to images first)

    Features:
    - GPU acceleration (CUDA/ROCm)
    - CPU fallback
    - Batch processing for efficiency
    - Automatic model downloading on first use
    """

    SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
    SUPPORTED_DOCUMENT_FORMATS = {".pdf"}  # For scanned PDFs
    SUPPORTED_FORMATS = SUPPORTED_IMAGE_FORMATS | SUPPORTED_DOCUMENT_FORMATS

    def __init__(self, device: str = "auto", batch_size: int = 4):
        """Initialize DeepSeek-OCR converter.

        Args:
            device: Device to run on - "auto", "cuda", "cpu", "mps" (Apple Silicon)
            batch_size: Number of images to process in parallel
        """
        self.device = self._get_device(device)
        self.batch_size = batch_size
        self._model = None
        self._tokenizer = None
        self._initialized = False

        logger.info(f"DeepSeek-OCR initialized with device: {self.device}")

    def _get_device(self, device: str) -> str:
        """Determine optimal device for inference."""
        if device != "auto":
            return device

        try:
            import torch

            if torch.cuda.is_available():
                logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
                return "cuda"
            elif torch.backends.mps.is_available():
                logger.info("Apple Metal (MPS) available")
                return "mps"
            else:
                logger.info("Using CPU (no GPU detected)")
                return "cpu"
        except ImportError:
            logger.warning("PyTorch not installed, defaulting to CPU")
            return "cpu"

    def _ensure_model_loaded(self):
        """Lazy load DeepSeek-OCR model (downloads on first use)."""
        if self._initialized:
            return

        try:
            from transformers import AutoModel, AutoTokenizer
            import torch
        except ImportError:
            raise Exception(
                "DeepSeek-OCR requires transformers and torch packages. "
                "Install with: pip install transformers torch"
            )

        logger.info("Loading DeepSeek-OCR model (this may take a few minutes on first run)...")

        try:
            # Load tokenizer (used by model.infer() method)
            self._tokenizer = AutoTokenizer.from_pretrained(
                "deepseek-ai/DeepSeek-OCR",
                trust_remote_code=True
            )

            # Load model with custom infer() method
            # Use bfloat16 for better stability on CUDA (avoids dtype mismatch), float32 on CPU
            if self.device == "cuda":
                dtype = torch.bfloat16
            else:
                dtype = torch.float32

            self._model = AutoModel.from_pretrained(
                "deepseek-ai/DeepSeek-OCR",
                trust_remote_code=True,
                torch_dtype=dtype
            )

            # Move model to device
            self._model = self._model.to(self.device)
            self._model.eval()  # Set to evaluation mode

            self._initialized = True
            logger.info(f"✓ DeepSeek-OCR model loaded on {self.device}")

        except Exception as e:
            logger.error(f"Failed to load DeepSeek-OCR model: {e}")
            raise Exception(f"DeepSeek-OCR model loading failed: {e}")

    async def convert_batch(self, file_paths: List[str]) -> Dict[str, str]:
        """Convert images and PDFs to markdown using DeepSeek-OCR.

        Args:
            file_paths: List of image/PDF file paths

        Returns:
            Dict mapping file_path -> extracted text (None if failed)
        """
        # Ensure model is loaded
        self._ensure_model_loaded()

        logger.info(f"Converting {len(file_paths)} documents with DeepSeek-OCR...")

        # Separate PDFs from images
        pdf_files = []
        image_files = []

        for path in file_paths:
            _, ext = os.path.splitext(path)
            ext = ext.lower()

            if ext in self.SUPPORTED_DOCUMENT_FORMATS:
                pdf_files.append(path)
            elif ext in self.SUPPORTED_IMAGE_FORMATS:
                image_files.append(path)
            else:
                logger.warning(f"Unsupported file format: {path}")

        results = {}

        # Process PDFs (convert to images first)
        if pdf_files:
            pdf_results = await self._process_pdfs(pdf_files)
            results.update(pdf_results)

        # Process images directly
        if image_files:
            image_results = await self._process_images(image_files)
            results.update(image_results)

        successful = sum(1 for r in results.values() if r)
        logger.info(f"DeepSeek-OCR complete: {successful}/{len(file_paths)} successful")

        return results

    async def _process_pdfs(self, pdf_paths: List[str]) -> Dict[str, str]:
        """Convert PDFs to images and then OCR them."""
        try:
            from pdf2image import convert_from_path
        except ImportError:
            logger.error("pdf2image package required for PDF OCR but not installed")
            return {path: None for path in pdf_paths}

        results = {}
        semaphore = asyncio.Semaphore(2)  # Limit concurrent PDF processing

        async def _process_one_pdf(pdf_path: str):
            async with semaphore:
                try:
                    logger.debug(f"Converting PDF to images: {os.path.basename(pdf_path)}")

                    # Convert PDF pages to images
                    def _convert_pdf():
                        images = convert_from_path(pdf_path, dpi=300)
                        return images

                    images = await asyncio.to_thread(_convert_pdf)

                    if not images:
                        logger.warning(f"No pages extracted from PDF: {pdf_path}")
                        results[pdf_path] = None
                        return

                    logger.debug(f"Extracted {len(images)} pages from {os.path.basename(pdf_path)}")

                    # OCR each page
                    page_texts = []
                    for i, img in enumerate(images):
                        text = await self._ocr_single_image(img, f"page_{i+1}")
                        if text:
                            page_texts.append(f"## Page {i+1}\n\n{text}")

                    if page_texts:
                        results[pdf_path] = "\n\n---\n\n".join(page_texts)
                        logger.debug(f"OCR completed for {os.path.basename(pdf_path)}")
                    else:
                        logger.warning(f"No text extracted from PDF: {pdf_path}")
                        results[pdf_path] = None

                except Exception as e:
                    logger.error(f"PDF processing failed for {pdf_path}: {e}")
                    results[pdf_path] = None

        await asyncio.gather(*[_process_one_pdf(p) for p in pdf_paths], return_exceptions=True)

        return results

    async def _process_images(self, image_paths: List[str]) -> Dict[str, str]:
        """Process image files with DeepSeek-OCR."""
        results = {}

        # Process in batches for GPU efficiency
        for i in range(0, len(image_paths), self.batch_size):
            batch_paths = image_paths[i:i + self.batch_size]
            batch_results = await self._process_image_batch(batch_paths)
            results.update(batch_results)

        return results

    async def _process_image_batch(self, image_paths: List[str]) -> Dict[str, str]:
        """Process a batch of images together (GPU-efficient)."""
        results = {}

        for path in image_paths:
            try:
                # Load image
                img = Image.open(path).convert("RGB")

                # OCR the image
                text = await self._ocr_single_image(img, os.path.basename(path))

                if text:
                    results[path] = text
                    logger.debug(f"OCR completed: {os.path.basename(path)} ({len(text)} chars)")
                else:
                    logger.warning(f"No text extracted from: {path}")
                    results[path] = None

            except Exception as e:
                logger.error(f"Image processing failed for {path}: {e}")
                results[path] = None

        return results

    async def _ocr_single_image(self, image: Image.Image, name: str) -> str:
        """Run OCR on a single PIL Image using DeepSeek-OCR.

        Args:
            image: PIL Image object
            name: Image name for logging

        Returns:
            Extracted text or None if failed
        """
        def _run_ocr():
            try:
                import torch
                import tempfile
                import os

                # DeepSeek-OCR's infer() method expects an image file path
                # Save PIL image to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                    tmp_path = tmp_file.name
                    image.save(tmp_path, format='PNG')

                # Create temporary output directory for model's internal use
                with tempfile.TemporaryDirectory() as tmp_output_dir:
                    try:
                        # Use DeepSeek-OCR's custom infer() method
                        # Prompt for pure OCR without layout grounding
                        prompt = "<image>\n<|grounding|>OCR this image."

                        # Call model's custom infer method
                        result = self._model.infer(
                            self._tokenizer,
                            prompt=prompt,
                            image_file=tmp_path,
                            output_path=tmp_output_dir,  # Temporary directory for model's internal files
                            base_size=1024,    # Standard base size
                            image_size=640,    # Standard image size
                            crop_mode=True,    # Use crop mode for better results
                            save_results=False, # Don't save intermediate files
                            test_compress=False  # No compression testing needed
                        )

                        # Extract text from result
                        # The infer method returns text output
                        if result and isinstance(result, str):
                            return result.strip() if result.strip() else None
                        else:
                            logger.warning(f"Unexpected result type from infer(): {type(result)}")
                            return None

                    finally:
                        # Clean up temp image file
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)

            except Exception as e:
                logger.error(f"OCR inference failed for {name}: {e}", exc_info=True)
                return None

        try:
            return await asyncio.to_thread(_run_ocr)
        except Exception as e:
            logger.error(f"OCR thread execution failed for {name}: {e}")
            return None
