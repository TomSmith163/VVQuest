import base64

from services.utils import *
from config.settings import config
import cv2
from PIL import Image, ImageEnhance
import io

PROMOTE = """你是一位表情包分类专家。请分析这个表情包，要求：

1. 简要分析表情包的内容，含义，主体和可能的使用场景；如果表情包有文字，你应该仔细分析考虑，因为表情包的文字通常有幽默感而难以理解；
2. 按格式要求输出表情包的文本描述，格式如下： **表情包含义**:(几个关键词概括表情包；如果表情包有文字，你要写出); **表情包主体**:(提取表情包的主角); **表情包使用场景**:(几个关键词描述表情包可能的使用场景)


"""

class LabelMemes():
    def __init__(self):
        self.api_key = config.api.silicon_api_key
        self.endpoint = "https://api.siliconflow.com/v1/embeddings"
        self.cache = {}
        self.use_cache = False
        self._load_cache()
        
        self.preprocess_config = {
            'max_size': 1024,        # 最大边长
            'quality': 5,           # png压缩质量
            'sharpen_factor': 1.5,   # 锐化强度
            'contrast_factor': 1.2   # 对比度增强
        }

    def _load_cache(self):
        cache_file = config.get_label_images_cache_file()
        verify_folder(cache_file)
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                self.cache = pickle.load(f)

    def _save_cache(self):
        cache_file = config.get_label_images_cache_file()
        with open(cache_file, 'wb') as f:
            pickle.dump(self.cache, f)

    def _analyze_result_text(self, text:str):
        """分析并格式化模型返回的文本"""
        if not '**表情包含义**' in text or not '**表情包主体**' in text or not '**表情包使用场景**' in text:
            raise Exception(f'analyze result text error: {text}; 模型太蠢,换个模型或者重试')
        desc = text.split('**表情包含义**')[-1]
        character = desc.split('**表情包主体**')[-1]
        usage = character.split('**表情包使用场景**')[-1]
        def clean_some_characters(x, l):
            for i in l:
                x = x.replace(i, '')
            return x
        desc = desc.replace(character, '')
        character = character.replace(usage, '')
        laji = ['表情包主体', '表情包使用场景', ':', '**(', ')；**', ');**', '**', ');', ')', '；', '(', ')', '\n', '：']
        desc = clean_some_characters(desc, laji).replace('/', ' ').replace('\\', ' ')
        character = clean_some_characters(character, laji).replace('/', ' ').replace('\\', ' ')
        usage = clean_some_characters(usage, laji).replace('/', ' ').replace('\\', ' ')
        return desc, character, usage

    def _resize_image(self, img):
        """尺寸调整"""
        h, w = img.shape[:2]
        max_size = self.preprocess_config['max_size']
        
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return img
    
    def _enhance_image(self, img):
        """图像增强"""
        # 转换为PIL格式进行处理
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        
        # 锐化处理
        enhancer = ImageEnhance.Sharpness(pil_img)
        pil_img = enhancer.enhance(self.preprocess_config['sharpen_factor'])
        
        # 对比度增强
        enhancer = ImageEnhance.Contrast(pil_img)
        pil_img = enhancer.enhance(self.preprocess_config['contrast_factor'])
        
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    

    def _compress_image(self, img):
        """格式转换与压缩"""
        encode_param = [int(cv2.IMWRITE_PNG_COMPRESSION), self.preprocess_config['quality']]
        _, img_encoded = cv2.imencode('.png', img, encode_param)
        return img_encoded

    def label_image(self, image_path):
        # 检查缓存
        model_name = config.models.vlm_models['Qwen2-VL-72B-Instruct'].name
        if not model_name in self.cache.keys():
            self.cache[model_name] = {}

        if get_file_hash(image_path) in self.cache[model_name] and self.use_cache:
            return self._analyze_result_text(self.cache[model_name][get_file_hash(image_path)]['description'])


        # 读取图像
        img = cv2.imread(image_path)
        
        # 尺寸调整（保持宽高比）
        img = self._resize_image(img)
        
        # 图像增强
        img = self._enhance_image(img)
        
        # 格式转换与压缩
        img_encoded = self._compress_image(img)

        img_str = base64.b64encode(img_encoded).decode("utf-8")

        import requests

        url = "https://api.siliconflow.cn/v1/chat/completions"

        payload = {
            "model": config.models.vlm_models['Qwen2-VL-72B-Instruct'].name,
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": PROMOTE
                        }
                    ]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f'data:image/png;base64,{img_str}',
                                "detail": "high"
                            }
                        }
                    ]
                }
            ]
        }
        headers = {
            "Authorization": f"Bearer {config.api.silicon_api_key}",
            "Content-Type": "application/json"
        }



        '''return type:
        {
      "id" : "123456789",
      "object" : "chat.completion",
      "created" : 123456789,
      "model" : "Qwen/Qwen2-VL-72B-Instruct",
      "choices" : [ {
        "index" : 0,
        "message" : {
          "role" : "assistant",
          "content" : "表情包含义:一只棕色的狗狗对着镜头露出略带搞笑的笑意；表情包主体:一只棕色的狗狗；表情包使用场景:朋友间的日常聊天或用以表达一些喜悦或风趣的意思。"
        },
        "finish_reason" : "stop"
      } ],
      "usage" : {
        "prompt_tokens" : 1509,
        "completion_tokens" : 46,
        "total_tokens" : 1555
      },
      "system_fingerprint" : ""
        }
        '''

        try:
            response = requests.request("POST", url, json=payload, headers=headers)
            response.raise_for_status()  # 抛出详细的HTTP错误
            description = response.json()['choices'][0]['message']['content']
            
            # 缓存结果
            self.cache[model_name][get_file_hash(image_path)] = {
                'description': description,
                'raw': response.json()
            }
            self._save_cache()
            
            return self._analyze_result_text(description)
            
        except requests.exceptions.RequestException as e:
            if hasattr(e.response, 'status_code') and e.response.status_code == 400:
                # 尝试打印详细的错误信息
                error_msg = e.response.json() if e.response.text else "未知错误"
                print(f"API请求参数错误: {str(error_msg).replace(img_str, 'IMGDATA')}")
            raise RuntimeError(f"API请求失败: {str(e)}\n请求参数: {str(payload).replace(img_str, 'IMGDATA')}")

if __name__ == "__main__":
    lm = LabelMemes()
    print(lm.label_image(r".\data\images\不值得同情的.png"))