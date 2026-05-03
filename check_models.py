import google.generativeai as genai
import os

api_key = "AIzaSyBVA9G3gJJSQ3JLsO-oLYYD0pkwNPG2--0"
genai.configure(api_key=api_key)
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)
