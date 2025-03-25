# Chat Server

## Requirements

- Python 3.11 or higher
- Poetry
- Google Cloud Platform Account

## Get Started

1. Clone the repository

   ```bash
   git clone https://github.com/wise-ntust/chat-server.git
   ```

2. Install dependencies

   ```bash
   poetry install
   ```

3. Create a `.env` file

   ```bash
   cp .env.example .env
   ```

4. Edit the `.env` file with your own credentials

   ```bash
   GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com"
   GOOGLE_CLIENT_SECRET="xxx"
   POSTGRESQL_URL="postgresql://xxx:xxx@xxx:6543/xxx"
   MONGODB_URL="mongodb+srv://xxx:xxx@xxx.mongodb.net/?retryWrites=true&w=majority&appName=xxx"
   ```

   > [How to get Google Client ID and Secret](https://stack.zhanyongxiang.com/google-oauth)

5. Run the server

   ```bash
   poetry run chat-server
   ```

6. Access the server

   ```bash
   http://localhost:8000/docs
   ```
