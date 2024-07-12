import sys
import zmq
import flatbuffers
import numpy as np
import threading
from ContinuousData import *
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

address = "127.0.0.1"
port = 5555

context = zmq.Context()
tcp_address = f"tcp://{address}:{port}"
socket = context.socket(zmq.SUB)
socket.setsockopt_string(zmq.SUBSCRIBE, "")
socket.connect(tcp_address)
recording_duration_samples = 600000


buffer_size = 30000
num_channels_to_plot = 64
channel_data = np.zeros((num_channels_to_plot, buffer_size))
index = 0

class RealTimePlotter(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Real-Time Channel Data')
        self.setGeometry(100, 100, 1000, 600)
        
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.layout = QtWidgets.QVBoxLayout(self.central_widget)

        self.plot_widget = pg.PlotWidget()
        self.layout.addWidget(self.plot_widget)
        
        self.plots = []
        for i in range(num_channels_to_plot):
            self.plots.append(self.plot_widget.plot(pen=pg.mkPen(width=1)))
        
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen='r')
        self.plot_widget.addItem(self.vline)

        self.plot_widget.setYRange(-10, num_channels_to_plot * 10)  # Adjust based on your expected amplitude range
        self.plot_widget.setXRange(0, buffer_size)
        
        self.update_interval = 0.1  # Interval to update the plot in seconds

        self.plot_timer = QtCore.QTimer()
        self.plot_timer.timeout.connect(self.update_plot)
        self.plot_timer.start(int(self.update_interval * 1000))

    def update_plot(self):
        global channel_data, index
        for i in range(num_channels_to_plot):
            self.plots[i].setData(channel_data[i, :] + i * 10)  # Offset each line for better visibility
        self.vline.setPos(index)

def data_collection():
    global channel_data, index
    while True:
        try:
            # Non-blocking wait to receive a message
            message = socket.recv(flags=zmq.NOBLOCK)
            
            # Decode the message
            try:
                buf = bytearray(message)
                data = ContinuousData.GetRootAsContinuousData(buf, 0)
            except Exception as e:
                print(f"Impossible to parse the packet received - skipping to the next. Error: {e}")
                continue

            # Access fields based on the schema
            num_samples = data.NSamples()
            num_channels = data.NChannels()
            samples_flat = data.SamplesAsNumpy() / 2000.0  # Divide by 2000

            # Check if the total size matches
            total_elements = samples_flat.size
            expected_elements = num_samples * num_channels
            
            if total_elements == expected_elements:
                samples_reshaped = samples_flat.reshape((num_channels, num_samples))

                # Update rolling buffer for each channel
                for i in range(num_channels_to_plot):
                    new_data = samples_reshaped[i, :]  # Collect data from each channel
                    if index + num_samples < buffer_size:
                        channel_data[i, index:index+num_samples] = new_data
                    else:
                        part1 = buffer_size - index
                        part2 = num_samples - part1
                        channel_data[i, index:] = new_data[:part1]
                        channel_data[i, :part2] = new_data[part1:]
                index = (index + num_samples) % buffer_size

            else:
                print(f"Error: Expected {expected_elements} elements but got {total_elements}.")

        except zmq.Again:
            # No message received
            pass

def main():
    app = QtWidgets.QApplication(sys.argv)
    plotter = RealTimePlotter()
    plotter.show()

    # Start the data collection thread
    data_thread = threading.Thread(target=data_collection)
    data_thread.daemon = True
    data_thread.start()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
