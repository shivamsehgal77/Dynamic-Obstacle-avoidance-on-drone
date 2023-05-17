import cv2
from sensor_msgs.msg import Image as msg_Image
from cv_bridge import CvBridge, CvBridgeError
from std_msgs.msg import Header
import rospy
from rospy.numpy_msg import numpy_msg
from rospy_tutorials.msg import Floats
from sensor_msgs.msg import Image
import os
os.environ['ROS_PYTHON_VERSION'] = '3'  # Replace '3' with your desired OpenCV version
from cv_bridge import CvBridge, CvBridgeError
import sys
import os
import time

import numpy as np
import copy as copy
fps = 0
class ImageListener:
	def __init__(self, topic1, topic2):
		self.topic1 = topic1
		self.topic2 = topic2
		self.color_image = None
		self.bridge = CvBridge()
		self.sub1 = rospy.Subscriber(topic1, msg_Image, self.imageDepthCallback1,queue_size=10)
		self.sub2 = rospy.Subscriber(topic2, msg_Image, self.imageCallback2,queue_size=10)
		self.pub = rospy.Publisher('/obstacle_detections', msg_Image, queue_size=10)
		self.pub2 = rospy.Publisher('/UMaps', msg_Image, queue_size=10)
		self.Umaps = None
		self.obstacle_detections = None
	def imageDepthCallback1(self, data):
		cv_image = self.bridge.imgmsg_to_cv2(data, data.encoding)
		self.imagePublisher(cv_image)
	def imageCallback2(self, data):
		self.color_image = self.bridge.imgmsg_to_cv2(data, data.encoding)    
	def imagePublisher(self,cv_image):
		strt = time.time()
		
		depth_image = copy.deepcopy(cv_image)

		bin_size=200
		num_columns = depth_image.shape[1]
		histograms = np.zeros((bin_size, 1), dtype=np.int16)

		for col in range(num_columns):
			column_values = depth_image[:, col]
			histogram, _ = np.histogram(column_values, bins=bin_size, range=(0,3000))
			histograms = np.column_stack((histograms, histogram))

		focal_length = 382.681243896484
		T_poi = 500
		T_tho = 1800
		values = list(range(0, 3001, 15))  # Generate the list of values spaced in 50 divisions from 0 to 3000
		averages = []

		for i in range(len(values)-1):
			start = values[i]
			end = values[i+1]
			average = (start + end) / 2
			averages.append(average)


		dbin = np.array(averages)

		T_pois = focal_length * T_tho / (dbin)

		res=np.array(T_pois)
		final_arr = np.array(res>T_poi)
		indices = np.where(final_arr == True)

		normalized_image_UDepth = cv2.normalize(histograms, None, 0, 255, cv2.NORM_MINMAX)
		converted_image_UDepth = np.uint8(normalized_image_UDepth)
		_, binary_image = cv2.threshold(converted_image_UDepth, 15, 36, cv2.THRESH_BINARY)

		# Find contours in the binary image
		contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
		areas = []
		coords = []
		# Iterate through contours and draw bounding boxes
		for contour in contours:
			x, y, width, height = cv2.boundingRect(contour)
			areas.append(cv2.contourArea(contour))
			coords.append((x, y, width, height))

		#max of areas list index gets coords
		max_index = areas.index(max(areas))
		x, y, width, height = coords[max_index]
		# cv2.rectangle(converted_image, (x, y), (x + width, y + height), (255, 0, 0), 1)

		u_l, d_t = x, y
		u_r, d_b = x + width, y + height

		x_o_body = d_b
		y_o_body = ((u_l + u_r)*d_b) / (2*focal_length)
		l_o_body = 2*(d_b-d_t)
		w_o_body = (u_r - u_l)*d_b / focal_length

		coord_list=[]
		if (u_l>=depth_image.shape[1] or u_r>=depth_image.shape[1]):
			print("out of bounds")
		else:
			listulur =np.linspace(u_l,u_r,20,dtype=int)
			for j in listulur:
				for i in range(depth_image.shape[0]):
					if ((depth_image[i][j] > (d_t*15)) and (depth_image[i][j] < ((d_t+l_o_body)*15))):
						coord_list.append([i,j])

		coordinates = np.array(coord_list)
		# x_max, y_max, x_min, y_min = np.max(coordinates[:,0]), np.max(coordinates[:,1]), np.min(coordinates[:,0]), np.min(coordinates[:,1])
		if len(coordinates) > 0:
			x_max, y_max = np.max(coordinates, axis=0)
			x_min, y_min = np.min(coordinates, axis=0)
		else:
    		# Handle the case when coordinates are empty
			x_max, y_max, x_min, y_min = 0, 0, 0, 0

		#normalize and convert a depth image which is of 64 bit to 8 bit
		normalized_image_depth = cv2.normalize(depth_image, None, 0, 255, cv2.NORM_MINMAX)
		converted_image_depth = np.uint8(normalized_image_depth)
		h_t = x_min
		h_b = x_max
		z_o_body = (h_t+h_b)*d_b / (2*focal_length)

		height_o_body = (-h_t+h_b)*d_b*15 / focal_length
		# color_image = self.color_image
		if(z_o_body*15 < 1500):
			cv2.rectangle(converted_image_depth, (y_min, x_min), (y_max, x_max), (255, 0, 0), 2)
		# Define the font properties
		font = cv2.FONT_HERSHEY_SIMPLEX
		font_scale = 0.5
		color = (255, 0, 0)  # Text color in BGR format
		thickness = 1  # Thickness of the text
		global fps
		text = "ZPose_body: " + str(z_o_body*15) + " mm" + "FPS: " + str(fps) + "FPS"

		# Get the dimensions of the image
		image_height, image_width = converted_image_depth.shape[:2]

		# Calculate the size of the text
		(text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)

		# Calculate the position of the text (top right corner)
		text_position = (image_width - text_width - 10, text_height + 10)

		# Add the text to the image
		cv2.putText(converted_image_depth, text, text_position, font, font_scale, color, thickness)
		self.obstacle_detections = converted_image_depth
		self.Umaps = converted_image_UDepth
		end_t = time.time()
		global frame_count
		frame_count+=1
		fps = 1/(end_t-strt)
		print("Frame count:", frame_count)
		print("Time taken: ", end_t-strt)      



frame_count = 0
if __name__ == '__main__':
	rospy.init_node("depth_image_processor")
	# topic1 = '/camera/depth/image_rect_raw'  # check the depth image topic in your Gazebo environmemt and replace this with your
	topic1 = '/camera/aligned_depth_to_color/image_raw'
	topic2  = '/camera/color/image_raw'
	listener = ImageListener(topic1, topic2)
	rate = rospy.Rate(5)
	while not rospy.is_shutdown():
		obstacleframe = listener.obstacle_detections
		Umapframe = listener.Umaps
		if (obstacleframe is not None or Umapframe is not None):
			# modified_msg = listener.bridge.cv2_to_imgmsg(obstacleframe, encoding='mono8')
			# modified_msg.header = Header(stamp=rospy.Time.now())
			# listener.pub.publish(modified_msg)
			# modified_msg2 = listener.bridge.cv2_to_imgmsg(Umapframe, encoding='mono8')
			# modified_msg2.header = Header(stamp=rospy.Time.now())
			# listener.pub2.publish(modified_msg2)
			cv2.imshow("obstacle", obstacleframe)
			cv2.imshow("Umap", Umapframe)
			cv2.waitKey(1)
			# rate.sleep()
	cv2.destroyAllWindows()
	rospy.spin()
