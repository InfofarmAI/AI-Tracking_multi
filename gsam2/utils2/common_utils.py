import os
import json
import cv2
import numpy as np
from dataclasses import dataclass
import supervision as sv
import random

class CommonUtils:
    @staticmethod
    def creat_dirs(path):
        """
        Ensure the given path exists. If it does not exist, create it using os.makedirs.

        :param path: The directory path to check or create.
        """
        try: 
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                print(f"Path '{path}' did not exist and has been created.")
            else:
                print(f"Path '{path}' already exists.")
        except Exception as e:
            print(f"An error occurred while creating the path: {e}")

    @staticmethod
    def draw_masks_and_box_with_supervision(raw_image_path, mask_path, json_path, output_path):
        CommonUtils.creat_dirs(output_path)
        raw_image_name_list = os.listdir(raw_image_path)
        raw_image_name_list.sort()
        for raw_image_name in raw_image_name_list:
            image_path = os.path.join(raw_image_path, raw_image_name)
            image = cv2.imread(image_path)
            if image is None:
                raise FileNotFoundError("Image file not found.")
            # load mask
            mask_npy_path = os.path.join(mask_path, "mask_"+raw_image_name.split(".")[0]+".npy")
            mask = np.load(mask_npy_path)
            # get unique mask IDs
            unique_ids = np.unique(mask)
            
            # Initialize lists to store data
            all_object_masks = []
            all_object_boxes = []
            all_class_ids = []
            labels = []
            
            # load box information
            file_path = os.path.join(json_path, "mask_"+raw_image_name.split(".")[0]+".json")
            with open(file_path, "r") as file:
                json_data = json.load(file)
            
            class_id_counter = 0  # For assigning integer class IDs
            
            for uid in unique_ids:
                if uid == 0:
                    continue  # Skip background
                uid_str = str(uid)
                if uid_str in json_data["labels"]:
                    obj_item = json_data["labels"][uid_str]
                    instance_id = obj_item["instance_id"]  # This can be a string
                    class_name = obj_item["class_name"]
                    x1, y1, x2, y2 = obj_item["x1"], obj_item["y1"], obj_item["x2"], obj_item["y2"]
                    
                    # get object mask
                    object_mask = (mask == uid)[None]  # Add new axis for concatenation
                    all_object_masks.append(object_mask)
                    all_object_boxes.append([x1, y1, x2, y2])
                    all_class_ids.append(class_id_counter)
                    labels.append(f"{instance_id}: {class_name}")
                    class_id_counter += 1
                else:
                    print(f"UID {uid} not found in labels for image {raw_image_name}")
                    continue
            
            if len(all_object_boxes) == 0:
                print(f"No objects found in image {raw_image_name}")
                continue
            
            # Concatenate all masks: (n, h, w)
            all_object_masks = np.concatenate(all_object_masks, axis=0)
            
            detections = sv.Detections(
                xyxy=np.array(all_object_boxes),
                mask=all_object_masks,
                class_id=np.array(all_class_ids, dtype=np.int32),
            )
            
            # Annotate the image
            box_annotator = sv.BoxAnnotator()
            annotated_frame = box_annotator.annotate(scene=image.copy(), detections=detections)
            label_annotator = sv.LabelAnnotator()
            annotated_frame = label_annotator.annotate(annotated_frame, detections=detections, labels=labels)
            mask_annotator = sv.MaskAnnotator()
            annotated_frame = mask_annotator.annotate(scene=annotated_frame, detections=detections)
            
            output_image_path = os.path.join(output_path, raw_image_name)
            cv2.imwrite(output_image_path, annotated_frame)
            print(f"Annotated image saved as {output_image_path}")

    @staticmethod
    def draw_masks_and_box(raw_image_path, mask_path, json_path, output_path):
        CommonUtils.creat_dirs(output_path)
        raw_image_name_list = os.listdir(raw_image_path)
        raw_image_name_list.sort()
        for raw_image_name in raw_image_name_list:
            image_path = os.path.join(raw_image_path, raw_image_name)
            image = cv2.imread(image_path)
            if image is None:
                raise FileNotFoundError("Image file not found.")
            # load mask
            mask_npy_path = os.path.join(mask_path, "mask_"+raw_image_name.split(".")[0]+".npy")
            mask = np.load(mask_npy_path)
            # color map
            unique_ids = np.unique(mask)
            colors = {uid: CommonUtils.random_color() for uid in unique_ids}
            colors[0] = (0, 0, 0)  # background color

            # apply mask to image in RBG channels
            colored_mask = np.zeros_like(image)
            for uid in unique_ids:
                colored_mask[mask == uid] = colors[uid]
            alpha = 0.5  # 调整 alpha 值以改变透明度
            output_image = cv2.addWeighted(image, 1 - alpha, colored_mask, alpha, 0)


            file_path = os.path.join(json_path, "mask_"+raw_image_name.split(".")[0]+".json")
            with open(file_path, 'r') as file:
                json_data = json.load(file)
                # Draw bounding boxes and labels
                for obj_id, obj_item in json_data["labels"].items():
                    # Extract data from JSON
                    x1, y1, x2, y2 = obj_item["x1"], obj_item["y1"], obj_item["x2"], obj_item["y2"]
                    instance_id = obj_item["instance_id"]
                    class_name = obj_item["class_name"]

                    # Draw rectangle
                    cv2.rectangle(output_image, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    # Put text
                    label = f"{instance_id}: {class_name}"
                    cv2.putText(output_image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                # Save the modified image
                output_image_path = os.path.join(output_path, raw_image_name)
                cv2.imwrite(output_image_path, output_image)

                print(f"Annotated image saved as {output_image_path}")

    @staticmethod
    def random_color():
        """random color generator"""
        return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
