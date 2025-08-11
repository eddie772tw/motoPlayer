MotoPlayer 專案環境手動安裝指南
文件版本: 1.0

簡介
本文件旨在引導開發者在一個乾淨的 Debian / Raspberry Pi OS 環境中，手動完成 MotoPlayer 後端應用程式的完整執行環境設定。

所有步驟均來自於 setup.sh 自動化安裝腳本，此處將其分解以便於理解和偵錯。

安裝流程
步驟 1: 更新套件列表並安裝系統級依賴
這個步驟會確保系統的套件列表是最新狀態，並安裝執行本專案所需的基礎軟體，包含 Python 環境、藍牙相關工具等。

請在終端機中執行以下指令：

sudo apt-get update
sudo apt-get install -y python3-pip python3-venv bluetooth bluez libbluetooth-dev rfcomm

步驟 2: 建立並啟用 Python 虛擬環境
為了保持專案依賴的獨立性，我們將建立一個專屬的 Python 虛擬環境。

建立虛擬環境 (如果 moto_env 資料夾不存在的話)：

python3 -m venv moto_env

啟用虛擬環境：

source moto_env/bin/activate

成功啟用後，您應該會在終端機的提示符前看到 (moto_env) 的字樣。

步驟 3: 安裝 Python 依賴套件
此步驟會讀取專案中的 requirements.txt 檔案，並自動安裝所有必要的 Python 函式庫。

請確保您已處於 moto_env 虛擬環境中。

pip install -r requirements.txt

步驟 4: 設定並啟用必要的藍牙系統服務
這一步是確保 Raspberry Pi 的藍牙能夠穩定運作，並與我們的 OBD-II 診斷器相容的關鍵。

啟用 hciuart 服務 (解決 Pi 特有的底層驅動問題)：

sudo systemctl enable hciuart.service

為 bluetooth 服務建立相容模式的覆蓋設定：
這個設定會強制藍牙服務以相容模式啟動，解決 profile-unavailable 的連線錯誤。

a. 建立覆蓋設定的目錄：

sudo mkdir -p /etc/systemd/system/bluetooth.service.d

b. 使用 printf 指令直接寫入設定檔，避免手動編輯：

printf "[Service]\nExecStart=\nExecStart=/usr/lib/bluetooth/bluetoothd -C\n" | sudo tee /etc/systemd/system/bluetooth.service.d/override.conf > /dev/null

重載 systemd 設定，讓剛剛的修改生效：

sudo systemctl daemon-reload

步驟 5: 初始化專案資料庫
此步驟會執行 Python 腳本來建立並初始化專案所需的 SQLite 資料庫檔案。

請確保您已處於 moto_env 虛擬環境中。

python3 init_db.py

設定完成
恭喜！至此，MotoPlayer 的後端執行環境已手動設定完畢。

您可以隨時執行 deactivate 指令退出 Python 虛-擬環境。