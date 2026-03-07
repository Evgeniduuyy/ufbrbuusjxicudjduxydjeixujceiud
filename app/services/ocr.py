import cv2
import numpy as np
from PIL import Image
import io
import easyocr
from app.config import Config
from app.celery_app import celery_app


if Config.OCR_ENGINE == "paddle":
    ocr_engine = PaddleOCR(use_angle_cls=True, lang='ru', show_log=False)
else:
    ocr_engine = None

def preprocess_image(image_bytes: bytes) -> bytes:
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    denoised = cv2.fastNlMeansDenoising(gray, h=30)
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    is_success, buffer = cv2.imencode(".png", thresh)
    return buffer.tobytes()

@celery_app.task(bind=True, max_retries=3)
def ocr_task(self, image_bytes: bytes) -> str:
    try:
        processed = preprocess_image(image_bytes)
        if Config.OCR_ENGINE == "paddle":
            result = ocr_engine.ocr(processed, cls=True)
            text = " ".join([line[1][0] for line in result[0]])
        else:
            img = Image.open(io.BytesIO(processed))
            text = pytesseract.image_to_string(img, lang='rus+eng')
        return text.strip()
    except Exception as e:
        self.retry(exc=e, countdown=60)
