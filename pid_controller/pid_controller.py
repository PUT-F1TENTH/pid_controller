import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from simple_pid import PID
from control_interfaces.msg import Control
from tf_transformations import euler_from_quaternion
from math import sqrt, atan2, cos

from std_msgs.msg import Float32


class VESCPIDController(Node):
    def __init__(self):
        super().__init__("vesc_pid_controller")

        # declare PID parameters
        self.declare_parameters(namespace="", parameters=[
            ("kp", 40.0), ("ki", 0.0), ("kd", 0.0),
        ])
        self.pid = PID(self.get_parameter("kp").value, self.get_parameter("ki").value, self.get_parameter("kd").value)
        
        # variables to store previous position and timestamp
        self.last_position_x = None
        self.last_position_y = None
        self.last_timestamp = None

        self.speed_buffer = []
        self.control_output = 0

        # variables read from mpc control
        self.target_speed = 0.0
        self.steering_angle = 0.0
        self.brake = 0.0,
        self.mode = None
        
        # publishers and subscribers
        self.vesc_command_publisher = self.create_publisher(Control, "commands/ctrl", 10)
        self.pose_subscription = self.create_subscription(PoseStamped, "optitrack/rigid_body_0", self.pose_callback, 10)
        self.control_command_subscription = self.create_subscription(Control, "mpc/control", self.control_command_callback, 1)

        # topics for debugging
        # self.estimated_speed = self.create_publisher(Float32, "estimated_speed", 10)
        # self.current = self.create_publisher(Float32, "current", 10)


    def pose_callback(self, msg):
        current_timestamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9

        if self.last_position_x and self.last_position_y and self.last_timestamp:

            # obtain differential position and time
            time_delta = current_timestamp - self.last_timestamp
            pos_diff_x = msg.pose.position.x - self.last_position_x
            pos_diff_y = msg.pose.position.y - self.last_position_y

            # calculate angle of car movement
            speed_angle = atan2(pos_diff_y, pos_diff_x)

            # get car orientation
            orientation = euler_from_quaternion([msg.pose.orientation.x,
                                                 msg.pose.orientation.y,
                                                 msg.pose.orientation.z, 
                                                 msg.pose.orientation.w])[2]

            # calculate absolute speed
            absolute_speed = sqrt(pos_diff_x**2 + pos_diff_y**2) / time_delta

            # calculate speed aligned with car orientation
            speed = absolute_speed * cos(speed_angle - orientation)

            # store last 10 speed values in buffer
            self.speed_buffer.append(speed)
            if len(self.speed_buffer) > 10:
                self.speed_buffer.pop(0)
            speed = sorted(self.speed_buffer)[len(self.speed_buffer) // 2]

            # pid things
            self.pid.setpoint = self.target_speed
            self.control_output = self.pid(speed)

            # self.get_logger().info(f"Sped angle: {speed_angle}")
            # self.get_logger().info(f"Orientation: {orientation}")
            # self.get_logger().info(f"Speed estimated: {speed}")
            # self.estimated_speed.publish(Float32(data=speed))
            # self.get_logger().info(f"Control output: {control_output}")
            # self.current.publish(Float32(data=control_output))
        
        self.last_position_x = msg.pose.position.x
        self.last_position_y = msg.pose.position.y
        self.last_timestamp = current_timestamp

    def control_command_callback(self, msg):
        self.target_speed = msg.set_speed
        self.steering_angle = msg.steering_angle
        self.brake = msg.set_brake

        if msg.control_mode is Control.SPEED_MODE:
            self.mode = Control.CURRENT_MODE
        elif msg.control_mode is Control.BRAKE_MODE:
            self.mode = Control.BRAKE_MODE
        
        self.send_motor_command()
        # self.get_logger().info(f"New target speed received: {msg.set_speed}")

    def send_motor_command(self):
        control = Control(
                set_current=self.control_output,
                set_brake=self.brake,
                steering_angle=self.steering_angle,
                control_mode=self.mode
            )
        self.vesc_command_publisher.publish(control)
        # self.get_logger().info(f"Sent motor current command: {current}")

def main(args=None):
    rclpy.init(args=args)
    vesc_controller = VESCPIDController()
    rclpy.spin(vesc_controller)
    vesc_controller.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
