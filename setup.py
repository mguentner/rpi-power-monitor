from setuptools import setup

setup(
   name='rpi-power-monitor',
   version='1.0',
   description='',
   author='David00',
   author_email='github@dalbrecht.tech',
   packages=['powermonitor'],
   install_requires=['requests', 'spidev', 'influxdb', 'prettytable', 'plotly'],
   scripts=["run_power_monitor"],
)
