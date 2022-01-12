import asyncio
import sys
import logging
import serial_asyncio
from serial.serialutil import SerialException
import serial_asyncio

from .crc import crc

_LOGGER = logging.getLogger(__name__)

abisolar_timeout = 5.0
base_delay = 0.1


def set_abisolar_timeout(t, d):
    global abisolar_timeout, base_delay
    abisolar_timeout = t
    base_delay = d


def init(r, w):
    global reader, writer
    reader = r
    writer = w


async def init_standalone():
    global reader, writer
    reader, writer = await serial_asyncio.open_serial_connection(
        url="/dev/ttyAMA0", baudrate=2400
    )
    await query_params()


def dbprint(line):
    out = ""
    for c in line:
        out = out + format(ord(c), "02x")
    return out


async def query_command_once(cmdname):
    cmd = cmdname + crc(cmdname) + "\x0d"
    _LOGGER.info("Prewrite %s %s", cmd, writer)
    try:
        writer.write(cmd.encode("latin-1"))
    except SerialException as exc:
        _LOGGER.exception("Afterwrite error %s %s", cmd, exc)
    # await writer.drain()
    _LOGGER.info("Afterwrite")
    await asyncio.sleep(base_delay)
    _LOGGER.info("Sleep finished")

    data = await reader.readuntil(separator=b"\r")
    data = data.decode("latin-1")

    if data is None:
        return None

    l = len(data)

    if l > 4:
        payload = data[0 : len(data) - 3]
        checksum = data[len(data) - 3 : len(data) - 1]
        pcrc = crc(payload)
        if checksum == pcrc:
            # print "recv finish:"+payload
            return payload[1:]
        else:
            _LOGGER.info("CRC fail")
            return None
    else:
        _LOGGER.info("Short packet")
        return None


async def query_command(cmdname):
    res = None
    for i in range(1, 2):
        res = await query_command_once(cmdname)
        if res:
            return res
        _LOGGER.info("Retry number %d", i)
        await asyncio.sleep(base_delay)
    _LOGGER.info("No valid responce after retries")
    return None


async def query_mode():
    def finish_mode(data):
        if (len(data) == 1) and data[0] in "PSLBFD":
            return data[0]
        else:
            return None

    return await query_command("QMOD", finish_mode)


async def query_settings():
    def finish_sett(data):
        vars = data.split(" ")
        try:
            outputSource = vars[16]
            chargeSource = vars[17]
            if (int(outputSource) in range(0, 5)) and (
                int(chargeSource) in range(0, 5)
            ):
                _LOGGER.info("OS %s %s", outputSource, chargeSource)
                return {"outputSource": outputSource, "chargeSource": chargeSource}
            else:
                _LOGGER.info("Some shitty info got")
                return None
        except ValueError:
            _LOGGER.info("Trash found in package")
            return None

    return await query_command("QPIRI", finish_sett)


def setOutputSource(val):
    _LOGGER.info("setting out source %s", val)

    data = query_command("POP" + val)
    v = data[:3] == "ACK"
    _LOGGER.info("From callback hello %s %s", data, v)
    return data


def pfloat(value):
    try:
        return float(value)
    except ValueError as e:
        _LOGGER.info("Error occured on parsing float value %d", value)
        return 0


async def query_params():

    _LOGGER.info("query_command")
    data = await query_command("QPIGS")
    vars = data.split(" ")

    data = ""
    try:
        out = {
            "gridVoltageR": float(vars[0]),
            "gridFrequency": float(vars[1]),
            "acOutputVoltageR": float(vars[2]),
            "acOutputFrequency": float(vars[3]),
            "acOutputApparentPower": float(vars[4]),
            "acOutputActivePower": float(vars[5]),
            "outputLoadPercent": float(vars[6]),
            "pBusVoltage": float(vars[7]),
            "pBatteryVoltage": float(vars[8]),
            "chargingCurrent": float(vars[9]),
            "batteryCapacity": float(vars[10]),
            "pvInputPower1": float(vars[11]),
            "pvInputCurrent": float(vars[12]),
            "pvInputVoltage1": float(vars[13]),
            "pvInputVoltage2": float(vars[14]),
            "batDischargeCurrent": float(vars[15]),
            "deviceStatus": vars[16],
        }

        _LOGGER.info("Out voltage %d", out["acOutputVoltageR"])
        _LOGGER.info(
            "PV power %d PV voltage %d  PV Current %d PV power %d",
            out["pvInputPower1"],
            out["pvInputVoltage1"],
            out["pvInputCurrent"],
            out["pvInputCurrent"] * out["pvInputVoltage1"],
        )
        _LOGGER.info(
            "Chargin' current %s discharge current %s",
            out["chargingCurrent"],
            out["batDischargeCurrent"],
        )
        _LOGGER.info(
            "Apparent Power %s Active Power %s Load percent %s",
            out["acOutputApparentPower"],
            out["acOutputActivePower"],
            out["outputLoadPercent"],
        )
        _LOGGER.info(
            "Battery volts %s battery percent %s",
            out["pBatteryVoltage"],
            out["batteryCapacity"],
        )

        _LOGGER.info("Returned %s", out)
        return out

    except ValueError:
        _LOGGER.info("Trash found in package")
        return None

    return None
