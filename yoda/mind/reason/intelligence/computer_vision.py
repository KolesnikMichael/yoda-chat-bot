import logging
import os
import base64
from mistralai import Mistral

logger = logging.getLogger(__name__)

class ComputerVision:
    def __init__(self, settings):
        self.mistral_client = Mistral(api_key=settings["pixtral_large_latest"]["api_key"])
        self.model_name = settings["pixtral_large_latest"]["model_name"]
        
    def encode_image_to_base64(self, image_file_path):
        with open(image_file_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
        
        
    def image_to_description(self, image_file_path):
        image_base64 = self.encode_image_to_base64(image_file_path)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please describe the image in detail."
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{image_base64}" 
                    }
                ]
            }
        ]

        chat_response = self.mistral_client.chat.complete(
            model=self.model_name,
            messages=messages)
        
        os.remove(image_file_path)
                
        return chat_response.choices[0].message.content