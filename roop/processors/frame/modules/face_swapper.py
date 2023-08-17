from typing import Any, List, Callable
import cv2
import insightface
import threading

import roop.globals
import roop.processors.frame.core as frame_processors
from roop.core import update_status
from roop.face_analyser import get_one_face, get_many_faces, find_similar_faces
from roop.face_reference import get_face_reference, set_face_reference, clear_face_reference
from roop.typing import Face, Frame
from roop.utilities import conditional_download, resolve_relative_path, is_image, is_video

FRAME_PROCESSOR = None
THREAD_LOCK = threading.Lock()
NAME = 'ROOP.FRAME_PROCESSOR.FACE_SWAPPER'


def get_frame_processor() -> Any:
    global FRAME_PROCESSOR

    with THREAD_LOCK:
        if FRAME_PROCESSOR is None:
            model_path = resolve_relative_path('../models/inswapper_128.onnx')
            FRAME_PROCESSOR = insightface.model_zoo.get_model(model_path, providers=roop.globals.execution_providers)
    return FRAME_PROCESSOR


def clear_frame_processor() -> None:
    global FRAME_PROCESSOR

    FRAME_PROCESSOR = None


def pre_check() -> bool:
    download_directory_path = resolve_relative_path('../models')
    conditional_download(download_directory_path, ['https://huggingface.co/henryruhs/roop/resolve/main/inswapper_128.onnx'])
    return True


def pre_start() -> bool:
    if not is_image(roop.globals.source_path):
        update_status('Select an image for source path.', NAME)
        return False
    elif not get_one_face(cv2.imread(roop.globals.source_path)):
        update_status('No face in source path detected.', NAME)
        return False
    if not is_image(roop.globals.target_path) and not is_video(roop.globals.target_path):
        update_status('Select an image or video for target path.', NAME)
        return False
    return True


def post_process() -> None:
    clear_frame_processor()
    clear_face_reference()


def swap_face(source_face: Face, target_face: Face, temp_frame: Frame) -> Frame:
    return get_frame_processor().get(temp_frame, target_face, source_face, paste_back=True)


def process_frame(source_face: Face, reference_face: Face, temp_frame: Frame) -> Frame:
    if 'reference' in roop.globals.face_recognition:
        similar_faces = find_similar_faces(temp_frame, reference_face, roop.globals.reference_face_distance)
        if similar_faces:
            for similar_face in similar_faces:
                temp_frame = swap_face(source_face, similar_face, temp_frame)
    if 'many' in roop.globals.face_recognition:
        many_faces = get_many_faces(temp_frame)
        if many_faces:
            for target_face in many_faces:
                temp_frame = swap_face(source_face, target_face, temp_frame)
    return temp_frame


def process_frames(source_path: str, temp_frame_paths: List[str], update: Callable[[], None]) -> None:
    source_face = get_one_face(cv2.imread(source_path))
    reference_face = get_face_reference() if 'reference' in roop.globals.face_recognition else None
    for temp_frame_path in temp_frame_paths:
        temp_frame = cv2.imread(temp_frame_path)
        result_frame = process_frame(source_face, reference_face, temp_frame)
        cv2.imwrite(temp_frame_path, result_frame)
        if update:
            update()


def process_image(source_path: str, target_path: str, output_path: str) -> None:
    source_face = get_one_face(cv2.imread(source_path))
    target_frame = cv2.imread(target_path)
    reference_face = get_one_face(target_frame, roop.globals.reference_face_position) if 'reference' in roop.globals.face_recognition else None
    result_frame = process_frame(source_face, reference_face, target_frame)
    cv2.imwrite(output_path, result_frame)


def process_video(source_path: str, temp_frame_paths: List[str]) -> None:
    conditional_set_face_reference(temp_frame_paths)
    frame_processors.process_video(source_path, temp_frame_paths, process_frames)


def conditional_set_face_reference(temp_frame_paths: List[str]) -> None:
    if 'reference' in roop.globals.face_recognition and not get_face_reference():
        reference_frame = cv2.imread(temp_frame_paths[roop.globals.reference_frame_number])
        reference_face = get_one_face(reference_frame, roop.globals.reference_face_position)
        set_face_reference(reference_face)