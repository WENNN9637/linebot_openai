#!/usr/bin/env python
# coding: utf-8

from flask import Flask, render_template, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextMessage, MessageEvent, TextSendMessage
import os
import openai
import tempfile
import datetime
import time
import string

import os

# 升級 openai 庫
os.system('pip install openai --upgrade')

# 使用 curl 下載 clinic_qa.json 文件
# os.system('curl -o clinic_qa.json -L https://github.com/Hsiang-Tang/gpt-3.5_fine_tune/raw/main/clinic_qa.json')

import openai

# 設置您的 OpenAI API 金鑰
openai.api_key = os.getenv("OPENAI_API_KEY")

# 創建聊天完成
completion = openai.ChatCompletion.create(
  model="gpt-4o",
  messages=[
    {"role": "user", "content": "Write a C program binary"}, 
    {"role": "assistant", "content": "#include \"search_algos.h\"\n\n/**\n * recursive_search - searches for a value in an array of\n * integers using the Binary search algorithm\n *\n *\n * @array: input array\n * @size: size of the array\n * @value: value to search in\n * Return: index of the number\n */\nint recursive_search(int *array, size_t size, int value)\n{\n\tsize_t half = size / 2;\n\tsize_t i;\n\n\tif (array == NULL || size == 0)\n\t\treturn (-1);\n\n\tprintf(\"Searching in array\");\n\n\tfor (i = 0; i < size; i++)\n\t\tprintf(\"%s %d\", (i == 0) ? \":\" : \",\", array[i]);\n\n\tprintf(\"\\n\");\n\n\tif (half && size % 2 == 0)\n\t\thalf--;\n\n\tif (value == array[half])\n\t\treturn ((int)half);\n\n\tif (value < array[half])\n\t\treturn (recursive_search(array, half, value));\n\n\thalf++;\n\n\treturn (recursive_search(array + half, size - half, value) + half);\n}\n\n/**\n * binary_search - calls to binary_search to return\n * the index of the number\n *\n * @array: input array\n * @size: size of the array\n * @value: value to search in\n * Return: index of the number\n */\nint binary_search(int *array, size_t size, int value)\n{\n\tint index;\n\n\tindex = recursive_search(array, size, value);\n\n\tif (index >= 0 && array[index] != value)\n\t\treturn (-1);\n\n\treturn (index);\n}"}
  ]
)

print(completion.choices[0].message.content)

# 創建帶有 fine-tuned 模型的聊天完成
completion2 = openai.ChatCompletion.create(
  model="ft:gpt-4o-2024-08-06:personal::B5sbnkYa",
  messages=[
    {"role": "user", "content": "Write a C program based on the file 1-binary.c:"}, 
    {"role": "assistant", "content": "```c\n#include \"search_algos.h\"\n\n/**\n * recursive_search - searches for a value in an array of\n * integers using the Binary search algorithm\n *\n * @array: input array\n * @size: size of the array\n * @value: value to search in\n * Return: index of the number\n */\nint recursive_search(int *array, size_t size, int value)\n{\n\tsize_t half = size / 2;\n\tsize_t i;\n\n\tif (array == NULL || size == 0)\n\t\treturn (-1);\n\n\tprintf(\"Searching in array\");\n\n\tfor (i = 0; i < size; i++)\n\t\tprintf(\"%s %d\", (i == 0) ? \":\" : \",\", array[i]);\n\n\tprintf(\"\\n\");\n\n\tif (half && size % 2 == 0)\n\t\thalf--;\n\n\tif (value == array[half])\n\t\treturn ((int)half);\n\n\tif (value < array[half])\n\t\treturn (recursive_search(array, half, value));\n\n\thalf++;\n\n\treturn (recursive_search(array + half, size - half, value) + half);\n}\n\n/**\n * binary_search - searches for a value in an array of\n * integers using the Binary search algorithm\n *\n * @array: input array\n * @size: size of the array\n * @value: value to search in\n * Return: index of the number\n */\nint binary_search(int *array, size_t size, int value)\n{\n\tint index;\n\n\tindex = recursive_search(array, size, value);\n\n\tif (index >= 0 && array[index] != value)\n\t\treturn (-1);\n\n\treturn (index);\n}\n```"}
  ]
)

print(completion2.choices[0].message.content)


def GPT_response(text):
    response = openai.ChatCompletion.create(
        model="ftjob-TJHXYaUkHGm9hHSqFxmQIuAq",
        messages=[
            {"role": "user", "content": "Write a C program binary"},
            {"role": "user", "content": text}
        ]
    )

    answer = response.choices[0].message.content

    # 去除回复文本中的標點符號
    answer = answer.translate(str.maketrans('', '', string.punctuation))

    return answer
