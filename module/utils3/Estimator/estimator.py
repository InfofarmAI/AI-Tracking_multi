import copy
import json


class PoseEstimator(object):
    def __init__(
        self,
        estimator_name='rtmpose',
        config_path=None,
        use_gpu=False,
    ):
        self.estimator_name = estimator_name
        self.estimator = None
        self.config = None
        self.use_gpu = use_gpu

       
        if self.estimator_name == 'rtmpose':
            from utils3.Estimator.rtmpose.rtmpose import RTMPose

            if self.use_gpu:
                # print("gpu")
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            else:
                # print("cpu")
                providers = ['CPUExecutionProvider']

            if config_path is None:
                config_path = 'module/utils3/Estimator/rtmpose/config.json'
            with open(config_path) as fp:
                self.config = json.load(fp)

            if self.config is not None:
                self.estimator = RTMPose(
                    model_path=self.config['model_path'],
                    providers=providers,
                )

        elif self.estimator_name == 'mediapipe_pose':
            from Estimator.mediapipe_pose.mediapipe_pose import MediapipePose

            # self.use_gpu = False  # GPU利用不可

            if config_path is None:
                config_path = 'Estimator/mediapipe_pose/config.json'
            with open(config_path) as fp:
                self.config = json.load(fp)

            if self.config is not None:
                self.estimator = MediapipePose(
                    model_complexity=self.config['model_complexity'],
                    min_detection_confidence=self.
                    config['min_detection_confidence'],
                    min_tracking_confidence=self.
                    config['min_tracking_confidence'],
                    static_image_mode=self.config['static_image_mode'],
                    plot_z_value=self.config['plot_z_value'],
                )

        else:
            raise ValueError('Invalid Estimator Name')

    def __call__(self, image, bboxes, bbox_offset):
        if self.estimator is not None:
            image_width, image_height = image.shape[1], image.shape[0]

            keypoints_list = []
            scores_list = []
            # for bbox in bboxes:
            x1, y1 = int(bboxes[0]) - bbox_offset, int(bboxes[1]) - bbox_offset
            x2, y2 = int(bboxes[2]) + bbox_offset, int(bboxes[3]) + bbox_offset
            if x1 < 0:
                x1 = 0
            if y1 < 0:
                y1 = 0
            if x2 >= image_width:
                x2 = image_width
            if y2 >= image_height:
                y2 = image_height

            crop_image = copy.deepcopy(image[y1:y2, x1:x2])
            if not (x2 - x1 > 0 and y2 - y1 > 0):
                return [],[]

            keypoints, scores = self.estimator(crop_image)

            if len(keypoints) == 0:
                return [],[]

            for index in range(len(keypoints)):
                # print(keypoints[17][0])
                # print(keypoints[17][1])
                keypoints[index][0] += x1
                keypoints[index][1] += y1
                # print("inidex",index)
                # print(keypoints[index][0])

            keypoints_list.append(keypoints)
            scores_list.append(scores)
        # else:
        #     raise ValueError('Estimator is None')

        return keypoints_list, scores_list

    def print_info(self):
        from pprint import pprint

        print('Estimator:', self.estimator_name)
        print('GPU:', self.use_gpu)
        pprint(self.config, indent=4)
        print()

    def draw(
        self,
        image,
        keypoints,
        scores,
        keypoint_score_th=0.6,
    ):
        return self.estimator.draw(image, keypoints, scores, keypoint_score_th)
