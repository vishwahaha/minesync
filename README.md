# MineSync: Decentralized Minecraft Server Hosting

MineSync is a serverless, peer-to-peer approach to hosting a Minecraft server among friends. Instead of paying for a 24/7 dedicated server to host your world, the world directory is stored securely on a Backblaze B2 cloud storage bucket.

The repository uses `rclone` to keep a 1:1 synchronized state. Only one player can run the server at a time, locked natively through hardware UUID mechanisms to prevent split-brain state, overwriting, or chunk corruption.

---

## 🚀 Getting Started

### 1. Configuration
A dummy `.env` file has been provided in the root directory. You must fill this out with your Backblaze B2 Application Key credentials.
Open `.env` in a text editor and add your details:

```env
B2_APP_KEY_ID=your_application_key_id_here
B2_APP_KEY=your_application_key_here
BUCKET_NAME=minecraft-data
```

### 2. Install Dependencies
Run the `setup.bat` script provided in the repository.
It utilizes native Windows `winget` installation paths to automatically check and install everything you need:
- Python 3
- Java (OpenJDK 17)
- Rclone
- Tailscale

The setup script will also read your `.env` file to instantly configure the `rclone` S3 remote for you. 
*(Note: Please restart your terminal/PC after running this for the first time to ensure the tools are available in your PATH).*

### 3. Server Preparation
1. Create a folder named `minecraft-world` in the same directory as this script.
2. Place your desired Minecraft `server.jar` inside the `minecraft-world` folder.
3. (Optional but recommended) Start the `.jar` manually once without the script to accept the EULA and generate base files.

### 4. Play!
Whenever someone wants to host the world, simply double-click or run:
```bash
python launcher.py
```

The script will automatically grab the lock, download the latest world data from the cloud, and start the Minecraft server. Your friends can join via your Tailscale IP! 
When you stop your server (using the `/stop` command in the console), the script automatically takes over, synchronizes the modified world map back to the cloud, and releases the lock for the next person!

---

## 📜 DOs and DON'Ts

### DO ✅
* **Use Tailscale:** Ensure all players are connected to the same Tailscale network using the IP outputted by the console to join the LAN safely without opening router ports.
* **Stop the server gracefully:** Always type `stop` into the Python Minecraft server console to turn it off. This tells the script to execute the cloud push phase. 
* **Back up the world periodically:** While Cloud storage provides intense durability, manually pushing your `minecraft-world/` folder into a ZIP on your laptop once a week remains best-practice.
* **Upgrade gracefully:** The system will allow you to run newer version servers (e.g. from `1.20` to `1.21`), which will securely rewrite your chunks with the new features locally before uploading. 

### DON'T ❌
* **Force-close the terminal:** Closing the terminal straight from the `X` button will kill Python instantly, skipping the crucial upload step resulting in lost playtime. Always type `stop`.
* **Share your `.env`:** These are permanent keys. They are kept safely in your local machine and your `.gitignore` naturally protects them. 
* **Downgrade server versions:** A robust semantic version check ensures you cannot load the world using a version older than its last run-state. Downgrading permanently corrupts generated chunks and voids player assets. 
* **Remove `state.json` externally:** The lock natively ensures two of you don't overwrite each other. Removing this from your cloud bucket manually breaks the synchronization queue! If you are sure a lock crashed and you need it reset natively, use `python launcher.py --force-unlock`.
