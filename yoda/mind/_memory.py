import logging
import time

logger = logging.getLogger(__name__)

class Memory:
    def __init__(self, mind, settings):
        self.settings = settings
        self.mind = mind