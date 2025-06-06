# from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
# from sam2.build_sam import build_sam2_video_predictor, build_sam2
# from sam2.sam2_image_predictor import SAM2ImagePredictor

# def initialize_models(device):
#     """ モデルをロードし、キャッシュを永続化 """
#     print(f"🚀 デバイス {device} でモデルをロード中...")

#     # SAM2 モデルのロード
#     sam2_checkpoint = "./gsam2/checkpoints/sam2_hiera_large.pt"
#     model_cfg = "sam2_hiera_l.yaml"
#     video_predictor = build_sam2_video_predictor(model_cfg, sam2_checkpoint)
#     sam2_image_model = build_sam2(model_cfg, sam2_checkpoint, device=device)
#     image_predictor = SAM2ImagePredictor(sam2_image_model)

#     # Grounding DINO モデルのロード
#     model_id = "IDEA-Research/grounding-dino-base"
#     processor = AutoProcessor.from_pretrained(model_id)
#     grounding_model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)

#     print("✅ モデルロード完了！")

#     return video_predictor, image_predictor, processor, grounding_model


# if __name__ == "__main__":
#     # VIDEO_PREDICTOR = None
#     # IMAGE_PREDICTOR = None
#     # PROCESSOR = None
#     # GROUNDING_MODEL = None
#     video_predictor, image_predictor, processor, grounding_model = initialize_models("cuda:0")


import torch
from sam2.build_sam import build_sam2_video_predictor, build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

# print("load_model")
# # モデルのキャッシュ
# video_predictor = None
# image_predictor = None
# processor = None
# grounding_model = None

# def load_models(device="cuda:0"):
#     global video_predictor, image_predictor, processor, grounding_model
#     if video_predictor is None or image_predictor is None or processor is None or grounding_model is None:
#         print("モデルをロード中...")
#         sam2_checkpoint = "./gsam2/checkpoints/sam2_hiera_large.pt"
#         model_cfg = "sam2_hiera_l.yaml"

#         video_predictor = build_sam2_video_predictor(model_cfg, sam2_checkpoint)
#         sam2_image_model = build_sam2(model_cfg, sam2_checkpoint, device=device)
#         image_predictor = SAM2ImagePredictor(sam2_image_model)

#         model_id = "IDEA-Research/grounding-dino-base"
#         processor = AutoProcessor.from_pretrained(model_id)
#         grounding_model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)

#     return video_predictor, image_predictor, processor, grounding_model

print("load_model")
device="cuda:0"
sam2_checkpoint = "./gsam2/checkpoints/sam2_hiera_large.pt"
model_cfg = "sam2_hiera_l.yaml"

VIDEO_PREDICTOR = build_sam2_video_predictor(model_cfg, sam2_checkpoint)
sam2_image_model = build_sam2(model_cfg, sam2_checkpoint, device=device)
IMAGE_PREDICTOR = SAM2ImagePredictor(sam2_image_model)

model_id = "IDEA-Research/grounding-dino-base"
PROCESSOR = AutoProcessor.from_pretrained(model_id)
GROUNDING_MODEL = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
print("完了")

