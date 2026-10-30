# Getting Started

This guide takes you from the downloaded zip file to the app running in your browser. No programming experience needed. Follow the section for your computer: **Mac** or **Windows**.

You do the **first-time setup** once. After that, use **Running the app again** each time.

---

## Before you start: install Python (one time)

The app needs Python 3.10 or newer.

**Check if you already have it**
- Mac: open Terminal (see Step 2 below), type `python3 --version`, press Enter.
- Windows: open Command Prompt (see Step 2 below), type `python --version`, press Enter.

If you see `Python 3.10` or a higher number, skip ahead to Step 1.

**If you don't have it**
1. Go to https://www.python.org/downloads/ and click the yellow **Download Python** button.
2. Open the downloaded file and follow the installer.
   - **Windows only:** on the first installer screen, tick the box **"Add python.exe to PATH"** before clicking Install. This is important.
3. When it finishes, close any Terminal or Command Prompt windows you have open, so the new install is picked up.

---

## Step 1: Put the project in a folder and unzip it

1. Create a folder for your projects, for example:
   - Mac: a folder named `Projects` inside your home folder (`/Users/yourname/Projects`)
   - Windows: `C:\Users\yourname\Projects`
2. Move `mortgage-preunderwriting-agent.zip` into that folder.
3. Unzip it:
   - Mac: double-click the zip file.
   - Windows: right-click the zip file, choose **Extract All...**, then click **Extract**.
4. You now have a folder named `mortgage-preunderwriting-agent`. Open it and confirm you see files such as `README.md`, `GETTING_STARTED.md`, `run.sh`, `run_windows.bat`, and folders `app`, `static`, `samples`.

> Windows note: "Extract All" sometimes creates a folder inside a folder (`mortgage-preunderwriting-agent\mortgage-preunderwriting-agent`). Use the inner one, the one that directly contains `README.md`.

Avoid putting the project inside iCloud Drive, OneDrive or Dropbox folders. The app stores uploaded documents in a `data` folder, and syncing can slow it down or copy borrower files to the cloud.

---

## Step 2: Open a terminal in the project folder

A terminal is a window where you type commands. You need it to be "in" the project folder.

### Mac

**Option A: from Finder (easiest)**
1. In Finder, go to the folder that *contains* `mortgage-preunderwriting-agent` (for example, `Projects`).
2. Right-click (or Control-click) the `mortgage-preunderwriting-agent` folder.
3. Choose **Services**, then **New Terminal at Folder**.

If you don't see that option, use Option B.

**Option B: drag and drop**
1. Press **Cmd + Space**, type `Terminal`, and press **Enter**.
2. In the Terminal window, type `cd` followed by one space. Do not press Enter yet.
3. Drag the `mortgage-preunderwriting-agent` folder from Finder and drop it into the Terminal window. The folder's location appears after `cd `.
4. Press **Enter**.

**Check you're in the right place:** type `ls` and press Enter. You should see `README.md`, `run.sh`, `app` and the other files listed. If not, repeat this step.

### Windows

**Option A: from File Explorer (easiest)**
1. In File Explorer, open the `mortgage-preunderwriting-agent` folder, so you're looking at `README.md`, `app`, `static` and the other files.
2. Click once in the **address bar** at the top of the window (where the folder path is shown). The path becomes highlighted.
3. Type `cmd` and press **Enter**. A black Command Prompt window opens, already in this folder.

**Option B: from the Start menu**
1. Click Start, type `cmd`, and press **Enter**.
2. In File Explorer, open the project folder, click the address bar, and copy the path (Ctrl + C).
3. In Command Prompt, type `cd /d ` (with a space at the end), paste the path (right-click or Ctrl + V), and press **Enter**.

**Check you're in the right place:** type `dir` and press Enter. You should see `README.md`, `run_windows.bat`, `app` and the other files listed.

---

## Step 3 (optional): Add your Anthropic API key

Without a key, the app runs in **offline demo mode**: it works with the two bundled sample loan files but cannot read real-world documents. With a key, Claude reads the PDFs, writes the advisor memo and answers questions.

To add a key:
1. Get an API key from https://console.anthropic.com (Settings, then API Keys).
2. In the project folder, make a copy of the file `.env.example` and name the copy `.env`.
   - Mac: in Terminal (still in the project folder), paste `cp .env.example .env` and press Enter, then open it with `open -e .env`.
   - Windows: in Command Prompt, paste `copy .env.example .env` and press Enter, then open it with `notepad .env`.
3. On the line `ANTHROPIC_API_KEY=`, paste your key right after the `=` sign, with no spaces. For example: `ANTHROPIC_API_KEY=sk-ant-...`
4. Save the file and close the editor.

> Files starting with a dot are hidden in Finder and File Explorer by default. That's why the commands above are the easiest way to create and edit `.env`.

You can add the key later. Just stop the app, add the key, and start it again.

---

## Step 4: First-time setup and launch

### Mac

In the Terminal window from Step 2, paste these lines **one at a time**, pressing **Enter** after each and waiting for it to finish:

```
chmod +x run.sh
```
```
./run.sh
```

The first run takes 1 to 3 minutes while it creates a private Python environment (a `.venv` folder) and installs what the app needs. You'll see some text scroll by. It's ready when you see a line like:

```
Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### Windows

**Easiest way:** in File Explorer, double-click **`run_windows.bat`** in the project folder. A window opens, sets everything up the first time (1 to 3 minutes), and starts the app.

**Or by typing commands:** in the Command Prompt window from Step 2, paste these lines **one at a time**, pressing **Enter** after each and waiting for it to finish:

```
python -m venv .venv
```
```
.venv\Scripts\python -m pip install -r requirements.txt
```
```
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

It's ready when you see a line like:

```
Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

If Windows shows a firewall prompt, you can click **Cancel** or **Allow**; the app only listens on your own computer.

---

## Step 5: Use the app

1. Open your web browser and go to **http://localhost:8000**
2. Click **Load sample A: clean purchase** or **Load sample B: problem file** in the left sidebar to see the agent work on synthetic loan files.
3. To work on your own files, click **New loan file**, go to the **Documents** tab, and drop PDFs onto the upload area.
4. Use the tabs to see **Rule results**, the **Advisor memo**, and **Ask the agent** questions.

**Keep the terminal window open while you use the app.** Closing it stops the app.

---

## Running the app again (after first-time setup)

Setup is done; you only need to start it.

### Mac
1. Open a terminal in the project folder (Step 2).
2. Paste this and press **Enter**:
   ```
   ./run.sh
   ```
3. Open **http://localhost:8000** in your browser.

### Windows
- Double-click **`run_windows.bat`** in the project folder,

  **or**

- Open Command Prompt in the project folder (Step 2), paste this and press **Enter**:
  ```
  .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  ```

Then open **http://localhost:8000** in your browser.

### Stopping the app
Click the terminal window and press **Ctrl + C** (on Mac too, it's Ctrl, not Cmd). Or just close the window.

Your loan files are saved in the project's `data` folder and will still be there next time.

---

## Troubleshooting

| What you see | What to do |
|---|---|
| `python3: command not found` (Mac) or `'python' is not recognized` (Windows) | Install Python (see the top of this guide). On Windows, make sure "Add python.exe to PATH" was ticked; if not, run the installer again, choose **Modify**, and tick it. Then open a new terminal window. |
| `./run.sh: Permission denied` (Mac) | Paste `chmod +x run.sh`, press Enter, then run `./run.sh` again. |
| `No such file or directory` or `cannot find the path` | The terminal isn't in the project folder. Repeat Step 2 and check with `ls` (Mac) or `dir` (Windows). |
| `Address already in use` or `port 8000` error | The app is already running in another window, or another program uses port 8000. Close the other window, or start on a different port: Mac `PORT=8001 ./run.sh`, Windows replace `8000` with `8001` in the start command. Then open http://localhost:8001. |
| Browser says "This site can't be reached" | The app isn't running. Check the terminal window is still open and shows the `Uvicorn running` line. |
| The sidebar says **Offline demo mode** although you added a key | Check the file is named exactly `.env` (not `.env.txt`), the key is on the `ANTHROPIC_API_KEY=` line with no spaces, then stop the app (Ctrl + C) and start it again. |
| Documents show **Error** after upload | Click **Review** on the document to see the error message. In Claude mode, this usually means the API key is invalid or out of credit. |
| Setup failed partway through | Delete the `.venv` folder inside the project folder and run the first-time setup again. |
