import logging


class Conversation:
  def __init__(self):
    # Dictionary to store conversations for each user, later to be inited from a database
    self.conversations = {}

  def add_line(self, user_id: int, chat_id: int, role="user", line=''):
    user = f"{user_id}@{chat_id}"
    if user not in self.conversations:
      logging.info(f"Starting new conversation with {user}")
      self.conversations[user] = [
          {"role": "system", "content": "Reply as Yoda from Star Wars"}]
    self.conversations[user].append({"role": role, "content": line})
    return self.conversations[user]
