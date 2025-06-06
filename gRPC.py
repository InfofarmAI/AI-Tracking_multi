import io
import cv2
import numpy as np
from PIL import Image
import multiprocessing

import CC_pb2
import CC_pb2_grpc

class CcServiceImpl(CC_pb2_grpc.CcServiceServicer):
    def __init__(self) -> None:
        super().__init__()
        self.camera_ids = {}
        self.instances = {}

    # 解析SVがフレーム読み込み込んだ時のイベント関数
    async def OnReadImg(self, request, context):
        
        def toMatLike(byte_img):
            num_byteio = io.BytesIO(byte_img)
            with Image.open(num_byteio) as img:
                ndArray_img = np.asarray(img)
            ndArray_img = cv2.cvtColor(ndArray_img, cv2.COLOR_BGR2RGB)
            # cv2.imwrite('./grpc.jpeg', ndArray_img)
            return ndArray_img
        
        # print(vars(request))
        byte_img, camera_settings = request.img, request.cameraSettings
        
        # バイト配列(画像)をモデルの入力形式(MatLike)に変換
        ndArray_img = toMatLike(byte_img)
        
        # カメラIDがなかったらインスタンス化 → 辞書に格納
        camera_id = camera_settings.cameraId
        if camera_id not in self.camera_ids.keys():
            self.camera_ids[camera_id] = camera_id
            camera = Camera(frame=ndArray_img, camera_settings=camera_settings, cameraId=camera_id)
            self.instances[camera_id] = camera
        else: # フレーム更新
            camera = self.instances[camera_id]
            camera.frame.put(ndArray_img)
        
        return CC_pb2.ImgResponse(msg="received")
    
    # CC解析時のイベント関数
    async def OnAnalyzedImg(self, request, context):
        # print(vars(request))
        camera = self.instances[request.cameraId]
        camera.datetime        = request.datetime
        camera.cameraId        = request.cameraId
        camera.ccDetailList[0] = request.ccDetailList
        return CC_pb2.CcResponse(msg="received")

class Camera():
    def __init__(self, frame, camera_settings, ccDetailList=None, datetime=None, cameraId=None) -> None:
        frame_queue = multiprocessing.Queue()
        frame_queue.put(frame)
        self.frame = frame_queue
        self.camera_settings = camera_settings
        manager = multiprocessing.Manager()
        list = manager.list()
        list.append(None)
        self.ccDetailList = list
        self.datetime = datetime
        self.cameraId = cameraId
        self.tracked_positions = manager.dict() # HACK メインプロセスでいじらないから共有にする必要なし？
        self.previous_frame_bboxes = []
        self.frame_count = 0  
