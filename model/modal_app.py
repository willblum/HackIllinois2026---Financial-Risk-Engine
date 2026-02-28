"""
Modal deployment for LLM inference.

Deploy once with:
    modal deploy backend/modal_app.py

Then call from FastAPI via modal.Cls.lookup("model-risk-llm", "LLM").

The deployed class exposes a single `.chat()` method that accepts OpenAI-style
messages and returns a string response.
"""

import modal

MODEL_NAME = "meta-llama/Llama-3.3-70B-Instruct"
APP_NAME = "model-risk-llm"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("vllm==0.6.6", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App(APP_NAME, image=image)

# HuggingFace secret needed to download gated Llama models.
# Create it with: modal secret create huggingface-secret HF_TOKEN=your_token
hf_secret = modal.Secret.from_name("huggingface-secret")


@app.cls(
    gpu="A10G",
    timeout=600,
    container_idle_timeout=300,
    secrets=[hf_secret],
)
class LLM:
    @modal.enter()
    def load_model(self):
        from vllm import LLM, SamplingParams
        self.llm = LLM(
            model=MODEL_NAME,
            max_model_len=4096,
            dtype="bfloat16",
        )
        self.SamplingParams = SamplingParams

    @modal.method()
    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.1,
    ) -> str:
        """
        OpenAI-style chat completion.
        messages: [{"role": "user"|"assistant"|"system", "content": "..."}]
        Returns the assistant's response as a plain string.
        """
        from vllm import SamplingParams
        params = SamplingParams(max_tokens=max_tokens, temperature=temperature)

        # vLLM applies the model's chat template automatically
        outputs = self.llm.chat(messages, sampling_params=params)
        return outputs[0].outputs[0].text.strip()


# --- Local entrypoint for quick testing ---
@app.local_entrypoint()
def main():
    llm = LLM()
    response = llm.chat.remote(
        messages=[{"role": "user", "content": "What is the Federal Reserve?"}],
        max_tokens=128,
    )
    print(response)
