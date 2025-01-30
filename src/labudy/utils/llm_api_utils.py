import time
import os
import asyncio
from typing_extensions import get_args
from tenacity import retry, wait_fixed, stop_after_attempt

import openai
from openai import OpenAI, AsyncOpenAI
import anthropic
from anthropic import Anthropic, AsyncAnthropic
import google.generativeai as genai
import google.api_core.exceptions as google_exceptions

def batch_response(models, params, messages):
    """
    Batch process synchronous LLM responses.
    """
    responses = {}
    for model_name in models:
        # Retrieve response from each model
        response = get_llm_response(model_name, params, messages)
        responses[model_name] = response
    return responses

async def batch_response_async(models, params, messages):
    """
    Batch process asynchronous LLM responses.
    """
    # Gather all async responses concurrently
    return await asyncio.gather(
        *[get_llm_response_async(model_name, params, messages) for model_name in models]
    )

def get_llm_response(model_name: str, params_: dict, messages: list[dict]) -> str:
    """
    Determines which LLM to call based on model_name and returns a response synchronously.
    """
    # Copy params to avoid mutating the original dictionary
    params = params_.copy()

    if model_name in OPENAI_MODEL_NAMES:
        # If max_tokens is found, copy it to max_completion_tokens for OpenAI usage
        if 'max_tokens' in params:
            params['max_completion_tokens'] = params['max_tokens']
            del params['max_tokens']
        return get_gpt_response(model_name, params, messages)

    elif model_name in ANTHROPIC_MODEL_NAMES:
        # Apply default max_tokens for Claude if not provided
        if 'max_tokens' not in params:
            params['max_tokens'] = 8192
        return get_claude_response(model_name, params, messages)

    elif model_name in GEMINI_MODEL_NAMES:
        return get_gemini_response(model_name, params, messages)

    else:
        # Notify if the specified model is not supported or no API key is set
        print("You need to set the API key for the model you want to use.")
        print("If OPENAI_API_KEY is set or not: ", 'OPENAI_API_KEY' in os.environ)
        print("If GOOGLE_API_KEY is set or not: ", 'GOOGLE_API_KEY' in os.environ)
        print("If ANTHROPIC_API_KEY is set or not: ", 'ANTHROPIC_API_KEY' in os.environ)
        raise ValueError(
            f"model_name {model_name} not supported. "
            f"Supported model names are: {OPENAI_MODEL_NAMES + ANTHROPIC_MODEL_NAMES + GEMINI_MODEL_NAMES}"
        )

@retry(wait=wait_fixed(90), stop=stop_after_attempt(10))
async def get_llm_response_async(model_name: str, params_: dict, messages: list[dict]) -> str:
    """
    Determines which LLM to call based on model_name and returns a response asynchronously.
    """
    # Copy params to avoid mutating the original dictionary
    params = params_.copy()

    if model_name in OPENAI_MODEL_NAMES:
        if 'max_tokens' in params:
            params['max_completion_tokens'] = params['max_tokens']
            del params['max_tokens']
        return await get_gpt_response_async(model_name, params, messages)

    elif model_name in ANTHROPIC_MODEL_NAMES:
        if 'max_tokens' not in params:
            params['max_tokens'] = 8192
        return await get_claude_response_async(model_name, params, messages)

    elif model_name in GEMINI_MODEL_NAMES:
        return await get_gemini_response_async(model_name, params, messages)

    else:
        raise ValueError(
            f"model_name {model_name} not supported. "
            f"Supported model names are: {OPENAI_MODEL_NAMES + ANTHROPIC_MODEL_NAMES + GEMINI_MODEL_NAMES}"
        )

def get_gpt_response(model_name: str, params: dict, messages: list[dict]) -> str:
    """
    Executes a synchronous call to an OpenAI-based LLM.
    """
    # Create OpenAI client
    client = OpenAI()
    # Make the chat completion request
    response = client.chat.completions.create(
        messages=messages,
        model=model_name,
        **params
    )
    # Return the content of the first choice
    return response.choices[0].message.content

async def get_gpt_response_async(model_name: str, params: dict, messages: list[dict]) -> str:
    """
    Executes an asynchronous call to an OpenAI-based LLM.
    """
    # Create an async OpenAI client
    client = AsyncOpenAI()
    # Make the async chat completion request
    response = await client.chat.completions.create(
        messages=messages,
        model=model_name,
        **params
    )
    # Return the content of the first choice
    return response.choices[0].message.content

def get_claude_response(model_name: str, params: dict, messages: list[dict]) -> str:
    """
    Executes a synchronous call to an Anthropic-based Claude LLM.
    """
    client = Anthropic()
    # Check if the first role is system; if so, provide separate system instruction
    if messages and messages[0]['role'] == 'system':
        response = client.messages.create(
            messages=messages[1:],  # Exclude the system instruction from messages
            model=model_name,
            system=messages[0]['content'],
            **params
        )
    else:
        response = client.messages.create(
            messages=messages,
            model=model_name,
            **params
        )
    # Return only the text content
    return response.content[0].text

async def get_claude_response_async(model_name: str, params: dict, messages: list[dict]) -> str:
    """
    Executes an asynchronous call to an Anthropic-based Claude LLM.
    """
    client = AsyncAnthropic()
    # Check if the first role is system; if so, provide separate system instruction
    if messages and messages[0]['role'] == 'system':
        response = await client.messages.create(
            messages=messages[1:],
            model=model_name,
            system=messages[0]['content'],
            **params
        )
    else:
        response = await client.messages.create(
            messages=messages,
            model=model_name,
            **params
        )
    return response.content[0].text

from google.generativeai.types import HarmCategory, HarmBlockThreshold
def get_gemini_response(model_name: str, params: dict, messages: list[dict]) -> str:
    """
    Executes a synchronous call to a Gemini-based LLM.
    """
    # Configure safety settings for Gemini
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    generation_config = parse_gemini_generation_config(params)
    # If first role is 'system', treat it as system instruction
    if messages and messages[0]['role'] == 'system':
        client = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
            system_instruction=messages[0]['content'],
        )
    else:
        client = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
        )
    gemini_messages = parse_gemini_messages(messages)
    response = client.generate_content(gemini_messages, safety_settings=safety_settings)
    return response.text

async def get_gemini_response_async(model_name: str, params: dict, messages: list[dict]) -> str:
    """
    Executes an asynchronous call to a Gemini-based LLM.
    """
    # Configure safety settings for Gemini
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    generation_config = parse_gemini_generation_config(params)
    # If first role is 'system', treat it as system instruction
    if messages and messages[0]['role'] == 'system':
        client = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
            system_instruction=messages[0]['content'],
        )
    else:
        client = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
        )
    gemini_messages = parse_gemini_messages(messages)

    try:
        response = await client.generate_content_async(gemini_messages, safety_settings=safety_settings)
        return response.text
    except ValueError as e:
        # This handles a known issue with the Gemini Python client
        print(e)
        print(response)
        return ''

def parse_gemini_generation_config(params: dict) -> dict:
    """
    Converts parameters for Gemini usage.
    """
    generation_config = {}
    for param_key in params:
        # Translate 'max_tokens' key to 'max_output_tokens'
        if param_key == 'max_tokens':
            generation_config['max_output_tokens'] = params[param_key]
        else:
            generation_config[param_key] = params[param_key]
    return generation_config

def parse_gemini_messages(messages: list[dict]) -> list[dict]:
    """
    Converts message format to Gemini-specific format.
    """
    gemini_messages = []
    for message in messages:
        gemini_message = {}
        # Identify role type
        if message['role'] == 'user':
            role = 'user'
        elif message['role'] == 'assistant':
            role = 'model'
        elif message['role'] == 'system':
            # Skip system role here since it is handled explicitly
            continue
        else:
            role = None

        gemini_message['role'] = role
        # Check if 'parts' exist, otherwise wrap content
        if 'parts' in message:
            gemini_message['parts'] = message['parts']
        else:
            gemini_message['parts'] = [message['content'] + '\n']
        gemini_messages.append(gemini_message)
    return gemini_messages

def get_gpt_model_names():
    """
    Retrieve the list of available GPT models using OpenAI client.
    """
    client = OpenAI()
    openai_model_names = [model_info.id for model_info in client.models.list().data]
    return openai_model_names

def get_gemini_model_names():
    """
    Retrieve the list of available Gemini models by invoking generative AI library.
    """
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    gemini_model_names = []
    for m in genai.list_models():
        # Check whether the model supports content generation
        if 'generateContent' in m.supported_generation_methods:
            gemini_model_names.append(m.name)
    return gemini_model_names

def get_anthropic_model_names():
    """
    Retrieve the list of available Anthropic models.
    """
    model_names = [
        model_name for model_name in get_args(get_args(anthropic.types.model.Model)[-1])
    ]
    return model_names

# Global model name lists based on environment variables
OPENAI_MODEL_NAMES = get_gpt_model_names() if 'OPENAI_API_KEY' in os.environ else []
GEMINI_MODEL_NAMES = get_gemini_model_names() if 'GOOGLE_API_KEY' in os.environ else []
ANTHROPIC_MODEL_NAMES = get_anthropic_model_names() if 'ANTHROPIC_API_KEY' in os.environ else []

if __name__ == '__main__':
    # Example usage of the code
    model_name = 'claude-3-5-sonnet-20240620'
    params = {
        'max_tokens': 256,
        'temperature': 0.0
    }
    messages = [
        {"role": "system", "content": "回答の際は、3つの回答を箇条書きで回答してください。"},
        {"role": "user", "content": "大喜利しましょう。とても面白い回答をしてくださいね。"},
        {"role": "assistant", "content": "おけ、任せて"},
        {"role": "user", "content": "こんな台風は嫌だ、どんな台風？"}
    ]

    # Synchronous single-model example
    response = get_llm_response(model_name, params, messages)
    print("Single model synchronous response:")
    print(response)

    # Synchronous batch example
    multiple_models = ['claude-3-5-sonnet-20240620', 'gpt-3.5-turbo']
    batch_sync_responses = batch_response(multiple_models, params, messages)
    print("\nBatch synchronous responses:")
    print(batch_sync_responses)

    async def main():
        # Asynchronous single-model example
        async_response = await get_llm_response_async(model_name, params, messages)
        print("\nSingle model asynchronous response:")
        print(async_response)

        # Asynchronous batch example
        async_batch_responses = await batch_response_async(multiple_models, params, messages)
        print("\nBatch asynchronous responses:")
        print(async_batch_responses)

    asyncio.run(main())