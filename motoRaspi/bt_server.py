# bt_server.py (v7.0 - dbus-fast 最終修正版)
# 修正潛在的 Race Condition 問題，並增加穩健的清理機制

import asyncio
import json
import requests
import logging
from typing import Dict, Any

from dbus_fast.service import ServiceInterface, method, dbus_property, PropertyAccess
from dbus_fast.aio import MessageBus

# --- 設定 (Configuration) ---
MOTOPLAYER_SERVICE_UUID = "a074c200-522d-4b83-a8e7-60453a55a36a"
DATA_CHAR_UUID = "a074c201-522d-4b83-a8e7-60453a55a36a"
COMMAND_CHAR_UUID = "a074c202-522d-4b83-a8e7-60453a55a36a"

FLASK_API_URL_REALTIME = "http://127.0.0.1:5000/api/realtime_data"
FLASK_API_URL_COMMAND = "http://127.0.0.1:5000/api/command"
DATA_POLLING_INTERVAL_S = 1.0

BLUEZ_SERVICE_NAME = 'org.bluez'
ADAPTER_PATH = '/org/bluez/hci0'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'


# --- 類別定義 (與 v5.4 版本相同，確保邏輯完整) ---
class Application(ServiceInterface):
    def __init__(self, bus):
        self.path = '/org/motoplayer'
        self.services = []
        self.bus = bus
        super().__init__(DBUS_OM_IFACE)

    def add_service(self, service):
        self.services.append(service)

    @method()
    def GetManagedObjects(self) -> 'a{oa{sa{sv}}}':
        objects = {self.path: {DBUS_OM_IFACE: {}}}
        for service in self.services:
            objects[service.path] = service.get_properties()
            for char in service.characteristics:
                objects[char.path] = char.get_properties()
        return objects


class MotoPlayerService(ServiceInterface):
    def __init__(self, bus, index):
        self.path = f'/org/motoplayer/service{index}'
        self.bus = bus
        self.characteristics = []
        super().__init__(GATT_SERVICE_IFACE)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': MOTOPLAYER_SERVICE_UUID,
                'Primary': True,
                'Characteristics': [c.path for c in self.characteristics]
            }
        }


class MotoPlayerCharacteristic(ServiceInterface):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f'{service.path}/char{index}'
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.service = service
        self._value = bytearray()
        super().__init__(GATT_CHRC_IFACE)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'UUID': self.uuid,
                'Service': self.service.path,
                'Flags': self.flags,
                'Value': self._value
            }
        }

    # ... (ReadValue, WriteValue, handle_command, notify 方法維持不變) ...
    @method()
    def ReadValue(self, options: 'a{sv}') -> 'ay':
        return self._value

    @method()
    def WriteValue(self, value: 'ay', options: 'a{sv}'):
        self._value = value;
        asyncio.create_task(self.handle_command(self._value))

    async def handle_command(self, value):
        # ... (此處邏輯不變) ...
        try:
            requests.post(FLASK_API_URL_COMMAND, json=json.loads(bytes(value).decode('utf-8')), timeout=2)
        except Exception as e:
            log.error(f"[CMD ERROR] {e}")

    def notify(self):
        self.bus.emit_signal(self.path, 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
                             ['sa{sv}as', [GATT_CHRC_IFACE, {'Value': self._value}, []]])


class DataCharacteristic(MotoPlayerCharacteristic):
    def __init__(self, bus, index, service):
        super().__init__(bus, index, DATA_CHAR_UUID, ['read', 'notify'], service)
        self.notifying = False

    @method()
    def StartNotify(self): self.notifying = True

    @method()
    def StopNotify(self): self.notifying = False


class Advertisement(ServiceInterface):
    def __init__(self, bus, index):
        self.path = f'/org/motoplayer/advertisement{index}'
        super().__init__('org.bluez.LEAdvertisement1')

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> 's': return 'peripheral'

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> 'as': return [MOTOPLAYER_SERVICE_UUID]

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> 's': return 'MotoPlayer_Pi'

    @dbus_property(access=PropertyAccess.READ)
    def IncludeTxPower(self) -> 'b': return True


# --- 背景任務 (維持不變) ---
async def data_pusher_loop(data_char: DataCharacteristic):
    while True:
        if data_char.notifying:
            try:
                response = await asyncio.get_running_loop().run_in_executor(None,
                                                                            lambda: requests.get(FLASK_API_URL_REALTIME,
                                                                                                 timeout=0.8))
                if response.status_code == 200:
                    new_value = response.text.encode('utf-8')
                    if new_value != data_char._value: data_char._value = new_value; data_char.notify()
            except Exception as e:
                log.error(f"[DATA ERROR] {e}")
        await asyncio.sleep(DATA_POLLING_INTERVAL_S)


# --- 主程式 ---
async def main():
    bus = await MessageBus(bus_address='unix:path=/var/run/dbus/system_bus_socket').connect()

    # 取得介面代理
    introspection = await bus.introspect(BLUEZ_SERVICE_NAME, ADAPTER_PATH)
    adapter_proxy = bus.get_proxy_object(BLUEZ_SERVICE_NAME, ADAPTER_PATH, introspection)
    gatt_manager = adapter_proxy.get_interface(GATT_MANAGER_IFACE)
    ad_manager = adapter_proxy.get_interface(LE_ADVERTISING_MANAGER_IFACE)

    # 建立應用程式物件
    app = Application(bus)
    service = MotoPlayerService(bus, 0)
    data_char = DataCharacteristic(bus, 0, service)
    command_char = MotoPlayerCharacteristic(bus, 1, COMMAND_CHAR_UUID, ['write', 'write-without-response'], service)
    service.add_characteristic(data_char);
    service.add_characteristic(command_char);
    app.add_service(service)
    advertisement = Advertisement(bus, 0)

    # 匯出所有物件到 D-Bus
    bus.export(app.path, app)
    bus.export(service.path, service)
    bus.export(data_char.path, data_char)
    bus.export(command_char.path, command_char)
    bus.export(advertisement.path, advertisement)

    # --- 【修改處】 ---
    # 增加一個短暫延遲，給予 D-Bus 服務足夠的時間來處理我們剛剛匯出的物件
    await asyncio.sleep(0.1)

    # 使用 try...finally 結構確保程式結束時能正確地取消註冊
    try:
        log.info("正在註冊 GATT 應用程式...")
        await gatt_manager.call_register_application(app.path, {})
        log.info("GATT 應用程式註冊成功！")

        log.info("正在註冊 BLE 廣播...")
        await ad_manager.call_register_advertisement(advertisement.path, {})
        log.info("BLE 廣播註冊成功！")

        print("--- [MotoPlayer BLE Bridge v7.0 - dbus-fast] ---")
        print(f"[*] BLE 應用程式已註冊並廣播")

        pusher_task = asyncio.create_task(data_pusher_loop(data_char))
        await bus.wait_for_disconnect()

    except Exception as e:
        log.error(f"註冊過程中發生錯誤: {e}")
    finally:
        log.info("正在取消註冊應用程式與廣播...")
        await ad_manager.call_unregister_advertisement(advertisement.path)
        await gatt_manager.call_unregister_application(app.path)
        log.info("清理完畢，程式結束。")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\n[*] 收到 Ctrl+C，正在關閉...")
