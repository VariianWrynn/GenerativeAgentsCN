import unittest
from unittest.mock import patch
from generative_agents.modules.model.llm_model import LLMModel, OpenAIModel # Assuming OpenAIModel is a concrete subclass we can use or mock

# A dummy config that can be used for LLMModel initialization if needed.
# Actual LLM calls will be mocked.
DUMMY_LLM_CONFIG = {
    "temperature": 0.7,
    "top_p": 1.0,
    "max_tokens": 256,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "request_timeout": 60,
}

class MockLLMModel(LLMModel):
    def __init__(self, predefined_responses=None, exception_on_calls=None, **kwargs):
        """
        predefined_responses: A list of strings or Exception objects.
                              If an Exception, it will be raised. Otherwise, returned.
        exception_on_calls: A dictionary mapping call_count (1-indexed) to an Exception to be raised.
        """
        # Call LLMModel's __init__ with minimal valid parameters.
        # We are mocking _completion, so actual API interaction won't happen.
        # If LLMModel.__init__ requires specific config keys, they should be provided.
        # For simplicity, we assume it can handle a basic setup or we mock its internal dependencies.

        # To avoid issues with base LLMModel __init__ trying to set up clients etc.,
        # we might need to patch more or ensure a very simple config.
        # Let's assume a simple config works or that the critical part is _completion.

        # Minimal super().__init__() call; may need adjustment based on LLMModel's actual constructor
        # If the base __init__ makes network calls or expects complex config, this part is tricky.
        # Patching 'openai.OpenAI' if it's called in __init__ of OpenAIModel might be needed.
        with patch('openai.OpenAI'): # Patch client creation if it happens in init
            super().__init__(base_url="http://mock", model_name="mock_model", keys={"mock_key": "mock_value"}, config=DUMMY_LLM_CONFIG)

        self.predefined_responses = predefined_responses if predefined_responses is not None else []
        self.exception_on_calls = exception_on_calls if exception_on_calls is not None else {}
        self._completion_call_count = 0
        self.current_response_index = 0

    def setup(self, keys, config):
        # Mock setup, do nothing or minimal setup
        self.config = config or DUMMY_LLM_CONFIG
        self.keys = keys
        # No actual client setup

    def _embedding(self, text):
        # Not testing embeddings here
        return [0.1, 0.2, 0.3]

    def _completion(self, prompt, **kwargs):
        self._completion_call_count += 1

        if self.exception_on_calls and self._completion_call_count in self.exception_on_calls:
            raise self.exception_on_calls[self._completion_call_count]

        if self.current_response_index < len(self.predefined_responses):
            response = self.predefined_responses[self.current_response_index]
            self.current_response_index += 1
            if isinstance(response, Exception):
                raise response
            # Simulate the structure that completion() expects from _completion()
            # which usually includes the raw response string and a place for meta.
            # The base class completion method adds to self.meta_responses.
            # Here, we just need to return the string content.
            return response
        else:
            raise Exception("MockLLMModel ran out of predefined responses.")

    def reset_call_count(self):
        self._completion_call_count = 0
        self.current_response_index = 0
        self.meta_responses = [] # Also clear meta_responses from base class

class TestLLMModelRetryMechanisms(unittest.TestCase):

    def test_retry_on_callback_failure_then_success(self):
        mock_llm = MockLLMModel(predefined_responses=["bad_output", "good_output"])

        def parsing_callback(response_text):
            if response_text == "bad_output":
                return None  # Simulate parsing failure
            elif response_text == "good_output":
                return "parsed_good_output"
            self.fail(f"Unexpected response_text in callback: {response_text}") # Should not happen

        result = mock_llm.completion(
            prompt="test prompt",
            caller="test_retry_on_callback_failure_then_success",
            retry=3,
            callback=parsing_callback,
            failsafe="failsafe_value"
        )

        self.assertEqual(mock_llm._completion_call_count, 2)
        self.assertEqual(result, "parsed_good_output")

    def test_exhaust_retries_and_return_failsafe(self):
        mock_llm = MockLLMModel(predefined_responses=["bad1", "bad2", "bad3", "bad4"]) # Provide enough for all retries

        def parsing_callback(response_text):
            if response_text.startswith("bad"):
                return None  # Simulate persistent parsing failure
            self.fail(f"Unexpected response_text in callback: {response_text}")

        result = mock_llm.completion(
            prompt="test prompt",
            caller="test_exhaust_retries_and_return_failsafe",
            retry=3,
            callback=parsing_callback,
            failsafe="expected_failsafe"
        )
        # Initial call + 2 retries = 3 calls
        self.assertEqual(mock_llm._completion_call_count, 3)
        self.assertEqual(result, "expected_failsafe")

    def test_immediate_success_no_retry(self):
        mock_llm = MockLLMModel(predefined_responses=["good_output"])

        def parsing_callback(response_text):
            if response_text == "good_output":
                return "parsed_good_output"
            self.fail(f"Unexpected response_text in callback: {response_text}")

        result = mock_llm.completion(
            prompt="test prompt",
            caller="test_immediate_success_no_retry",
            retry=3,
            callback=parsing_callback,
            failsafe="failsafe_value"
        )

        self.assertEqual(mock_llm._completion_call_count, 1)
        self.assertEqual(result, "parsed_good_output")

    def test_retry_on_exception_in_completion_then_success(self):
        # First call raises Exception, second call returns "good_output_after_exception"
        mock_llm = MockLLMModel(
            predefined_responses=[
                RuntimeError("Simulated API error on first call"),
                "good_output_after_exception"
            ]
        )

        # Simple callback that just returns the text, or no callback if LLMModel handles it
        def simple_callback(text):
            return text

        result = mock_llm.completion(
            prompt_hint="test_prompt_exception",
            retry=3, # Allow retries
            callback=simple_callback, # Callback is still called if _completion succeeds
            failsafe="failsafe_if_all_fail"
        )

        self.assertEqual(mock_llm._completion_call_count, 2)
        self.assertEqual(result, "good_output_after_exception")
        # Check that an error was logged by the LLMModel (optional, depends on logging setup)
        # For this, we might need to patch self.logger in LLMModel or check stderr if it prints there.

    def test_exhaust_retries_on_exception_and_return_failsafe(self):
        mock_llm = MockLLMModel(
            predefined_responses=[
                RuntimeError("Simulated API error 1"),
                RuntimeError("Simulated API error 2"),
                RuntimeError("Simulated API error 3"), # Enough errors for all 3 attempts
            ]
        )

        result = mock_llm.completion(
            prompt="test prompt",
            caller="test_exhaust_retries_on_exception_and_return_failsafe",
            retry=3,
            callback=lambda x: x, # Simple callback
            failsafe="expected_failsafe_after_exceptions"
        )
        # Initial call + 2 retries = 3 calls
        self.assertEqual(mock_llm._completion_call_count, 3)
        self.assertEqual(result, "expected_failsafe_after_exceptions")

if __name__ == '__main__':
    unittest.main()
