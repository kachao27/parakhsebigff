"""OCR feeding the text pipeline. Two backends, auto-selected:

- tesseract (eng+hin) where installed - the deployment path (Railway/Linux)
- Apple Vision framework on macOS dev machines without tesseract

Both feed the same downstream text path; backend choice never changes verdicts.
"""
import logging
import shutil

log = logging.getLogger("parakh.ocr")


def _tesseract(image_path: str) -> str:
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(image_path), lang="eng+hin")


def _apple_vision(image_path: str) -> str:
    import Quartz
    import Vision

    url = Quartz.NSURL.fileURLWithPath_(image_path)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        return ""
    cgimg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if cgimg is None:
        return ""

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(["en-IN", "hi-IN", "en-US"])
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cgimg, None)
    ok, _err = handler.performRequests_error_([request], None)
    if not ok or request.results() is None:
        return ""
    lines = []
    for obs in request.results():
        cand = obs.topCandidates_(1)
        if cand and len(cand):
            lines.append(str(cand[0].string()))
    return "\n".join(lines)


def extract_text(image_path: str) -> str:
    try:
        if shutil.which("tesseract"):
            return _tesseract(image_path)
        return _apple_vision(image_path)
    except Exception as e:
        log.warning("OCR failed: %s", e)
        return ""
