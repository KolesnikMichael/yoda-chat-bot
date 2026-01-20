import logging

logger = logging.getLogger(__name__)


class Emotions:
  def __init__(self, mind, settings):
    self.mind = mind
    self.glad = settings["glad"]
    self.mad = settings["mad"]
    self.sad = settings["sad"]
    self.scared = settings["scared"]

  def get_emotions(self):
    return {"glad": self.glad, "mad": self.mad, "sad": self.sad, "scared": self.scared}
