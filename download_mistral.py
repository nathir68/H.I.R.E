#!/usr/bin/env python3
"""
Download Mistral 7B in 8-bit quantized format
"""

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import os

def download_mistral_8bit():
    model_name = "mistralai/Mistral-7B-Instruct-v0.1"
    cache_dir = "./mistral_model"
    
    print("🚀 Starting Mistral 7B 8-bit download...")
    print(f"Model: {model_name}")
    print(f"Saving to: {cache_dir}")
    
    try:
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
        
        print("\n📥 Downloading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            trust_remote_code=True
        )
        print("✅ Tokenizer downloaded")
        
        print("\n📥 Downloading model in 8-bit quantization...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map="auto",
            load_in_8bit=True,
            cache_dir=cache_dir,
            trust_remote_code=True,
            torch_dtype=torch.float16
        )
        print("✅ Model downloaded and loaded")
        
        print(f"\n✨ Success! Model saved to: {os.path.abspath(cache_dir)}")
        print(f"\nModel size: ~7B parameters (8-bit quantized)")
        print(f"Tokenizer saved in: {os.path.abspath(cache_dir)}")
        
        return model, tokenizer
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None

if __name__ == "__main__":
    model, tokenizer = download_mistral_8bit()
    
    if model and tokenizer:
        print("\n" + "="*50)
        print("🎉 Ready to use!")
        print("="*50)
        print("\nQuick test:")
        
        prompt = "Hello, I am a"
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        
        with torch.no_grad():
            outputs = model.generate(**inputs, max_length=50)
        
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        print(f"\nPrompt: {prompt}")
        print(f"Response: {response}")
