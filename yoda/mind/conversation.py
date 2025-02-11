import logging

class Conversation:
    def __init__(self):
        self.conversations = {}  # Dictionary to store conversations for each user, later to be inited from a database

    
    def add(self, user, role="user", line=''):
        if user not in self.conversations:
            logging.info(f"Starting new conversation for user {user}")
            self.conversations[user] = [{"role": "system", "content": "Reply as Yoda from Star Wars"}]
        self.conversations[user].append({"role": role, "content": line})
        return self.conversations[user]