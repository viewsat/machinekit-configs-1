# coding=utf-8
# HAL file for BeagleBone + TCT paralell port cape with 5 steppers and 3D printer board
import os

from machinekit import rtapi as rt
from machinekit import hal
from machinekit import config as c

from fdm.config import velocity_extrusion as ve
from fdm.config import base
from fdm.config import storage
from fdm.config import motion
import hardware

# initialize the RTAPI command client
rt.init_RTAPI()
# loads the ini file passed by linuxcnc
c.load_ini(os.environ['INI_FILE_NAME'])

motion.setup_motion()
hardware.init_hardware()
storage.init_storage('storage.ini')

# Gantry component for Z Axis
base.init_gantry(axisIndex=2)

# reading functions
hardware.hardware_read()
base.gantry_read(gantryAxis=2, thread='servo-thread')
hal.addf('motion-command-handler', 'servo-thread')
hal.addf('motion-controller', 'servo-thread')

numFans = c.find('FDM', 'NUM_FANS')
numExtruders = c.find('FDM', 'NUM_EXTRUDERS')
numLights = c.find('FDM', 'NUM_LIGHTS')
withAbp = c.find('FDM', 'ABP', False)

# Axis-of-motion Specific Configs (not the GUI)
ve.velocity_extrusion(extruders=numExtruders, thread='servo-thread')
# X [0] Axis
base.setup_stepper(section='AXIS_0', axisIndex=0, stepgenIndex=0, thread='servo-thread')
# Y [1] Axis
base.setup_stepper(section='AXIS_1', axisIndex=1, stepgenIndex=1, thread='servo-thread')
# Z [2] Axis
base.setup_stepper(section='AXIS_2', axisIndex=2, stepgenIndex=2,
                   thread='servo-thread', gantry=True, gantryJoint=0)
base.setup_stepper(section='AXIS_2', axisIndex=2, stepgenIndex=3,
                   thread='servo-thread', gantry=True, gantryJoint=1)
# Extruder 0, velocity controlled
base.setup_stepper(section='EXTRUDER_0', stepgenIndex=4, velocitySignal='ve-extrude-vel-0')
# Extruder 1, velocity controlled
base.setup_stepper(section='EXTRUDER_1', stepgenIndex=5, velocitySignal='ve-extrude-vel-1')

# workaround for joint following error problem
# feed pos cmd straight back to the feedback channel
for i in range(3):
    pin = hal.Pin('axis.%i.motor-pos-fb' % i)
    pin.unlink()
    pin.link('emcmot-%i-pos-cmd' % i)

# Extruder Multiplexer
base.setup_extruder_multiplexer(extruders=(numExtruders + int(withAbp)), thread='servo-thread')
for n in range(numExtruders):
    mux = rt.newinst('muxn', 'mux-extruder-vel-{}'.format(n), pincount=numExtruders)
    hal.addf(mux.name, 'servo-thread')
    for i in range(numExtruders):
        mux.pin('in{}'.format(i)).set(0.0)
    mux.pin('in{}'.format(n)).link('ve-extrude-vel')
    mux.pin('out').link('ve-extrude-vel-{}'.format(n))
    mux.pin('sel').link('extruder-sel')

# ABP support
if withAbp:  # not a very good solution
    hal.Pin('motion.digital-out-io-20').link('stepgen-5-control-type')
    hal.net('stepgen-5-pos-cmd', 'motion.analog-out-io-50', 'hpg.stepgen.05.position-cmd')
    hal.net('stepgen-5-pos-fb', 'motion.analog-in-50', 'hpg.stepgen.05.position-fb')

# Fans
for i in range(0, numFans):
    base.setup_fan('f%i' % i, thread='servo-thread')
for i in range(0, numExtruders):
    hardware.setup_exp('exp%i' % i)

# Temperature Signals
base.create_temperature_control(name='hbp', section='HBP',
                                hardwareOkSignal='temp-hw-ok',
                                thread='servo-thread')
for i in range(0, numExtruders):
    base.create_temperature_control(name='e%i' % i, section='EXTRUDER_%i' % i,
                                    coolingFan='f%i' % i, hotendFan='exp%i' % i,
                                    hardwareOkSignal='temp-hw-ok',
                                    thread='servo-thread')

# LEDs
for i in range(0, numLights):
    base.setup_light('l%i' % i, thread='servo-thread')
# HB LED
hardware.setup_hbp_led(thread='servo-thread')

# Standard I/O - EStop, Enables, Limit Switches, Etc
errorSignals = ['gpio-hw-error', 'pwm-hw-error', 'temp-hw-error',
                'watchdog-error', 'hbp-error']
for i in range(0, numExtruders):
    errorSignals.append('e%i-error' % i)
base.setup_estop(errorSignals, thread='servo-thread')
base.setup_tool_loopback()
# Probe
base.setup_probe(thread='servo-thread')
# Setup Hardware
hardware.setup_hardware(thread='servo-thread')

# write out functions
base.gantry_write(gantryAxis=2, thread='servo-thread')
hardware.hardware_write()

# Storage
storage.read_storage()

# start haltalk server after everything is initialized
# else binding the remote components on the UI might fail
hal.loadusr('haltalk', wait=True)
