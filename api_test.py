# from flask import Flask, Response, render_template_string
# import cv2

# app = Flask(__name__)

# # カメラURLを辞書で管理
# CAMERA_URLS = {
#     0: "rtsp://192.168.1.148:554/rtpstream/config1",
#     1: "rtsp://192.168.1.147:554/rtpstream/config1"
#     # 2: "rtsp://192.168.1.143:554/rtpstream/config1",
# }

# def generate_stream(rtsp_url):
#     cap = cv2.VideoCapture(rtsp_url)
#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             break
#         _, jpeg = cv2.imencode('.jpg', frame)
#         yield (b'--frame\r\n'
#             b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

# @app.route('/')
# def index():
#     return render_template_string('''
#     <html>
#     <body>
#         <h1>RTSPカメラ映像（{{ camera_count }} 台）</h1>
#         <div style="display: flex; flex-wrap: wrap; gap: 20px;">
#         {% for cam_id in camera_ids %}
#             <div>
#                 <h3>Camera {{ cam_id + 1 }}</h3>
#                 <img src="/video_feed/{{ cam_id }}" style="max-width: 480px; max-height: 360px;">
#             </div>
#         {% endfor %}
#         </div>
#     </body>
#     </html>
#     ''', camera_ids=CAMERA_URLS.keys(), camera_count=len(CAMERA_URLS))

# @app.route('/video_feed/<int:cam_id>')
# def video_feed(cam_id):
#     rtsp_url = CAMERA_URLS.get(cam_id)
#     if rtsp_url is None:
#         return "Invalid camera ID", 404
#     return Response(generate_stream(rtsp_url),
#                     mimetype='multipart/x-mixed-replace; boundary=frame')

# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=8000, threaded=True, debug=True)


import datetime

dt = datetime.datetime(2025, 3, 13, 14, 18, 34)  # JSTでの入力
epoch_ms = int(dt.timestamp() * 1000)
print(epoch_ms)  # → 1741852714000
