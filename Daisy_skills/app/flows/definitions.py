from typing import Dict, Any

MAIN_DIALOGUE_FLOW = {
    "type": "switch",
    "router": {
        "skill": "router",
        "operation": "route_input",
        "inputs": {
            "user_input": "user_input",
            "user_id": "user_id",
            "session_id": "session_id",
            "context": "context"
        },
        "output_key": "route_result"
    },
    "cases": {
        "FAST": {
            "type": "chain",
            "steps": [
                {
                    "skill": "generation",
                    "operation": "chat",
                    "inputs": {
                        "user_input": "user_input",
                        "history": "history",
                        "context": "context"
                    },
                    "params": {
                        "system_prompt": "You are a helpful assistant. Keep your answers short and concise."
                    },
                    "output_key": "response"
                }
            ]
        },
        "STANDARD": {
            "type": "chain",
            "steps": [
                {
                    "type": "parallel",
                    "tasks": [
                        {
                            "skill": "emotion",
                            "operation": "analyze",
                            "inputs": {
                                "text": "user_input",
                                "user_id": "user_id",
                                "session_id": "session_id",
                                "language_hint": "language_hint",
                                "context_history": "history"
                            },
                            "output_key": "emotion_data"
                        },
                        {
                            "skill": "topic",
                            "operation": "summarize",
                            "inputs": {
                                "history": "history",
                                "latest_message": "latest_message",
                                "session_id": "session_id",
                                "language_hint": "language_hint"
                            },
                            "params": {
                                "max_tokens": 120
                            },
                            "output_key": "topic_summary"
                        }
                    ]
                },
                {
                    "skill": "memory",
                    "operation": "search",
                    "inputs": {
                        "query": "user_input",
                        "user_id": "user_id",
                        "session_id": "session_id",
                        "topic_summary": "topic_summary.summary"
                    },
                    "params": {
                        "limit": 5
                    },
                    "output_key": "memory_results"
                },
                {
                    "skill": "persona",
                    "operation": "select",
                    "inputs": {
                        "user_id": "user_id",
                        "emotion_scores": "emotion_data.scores",
                        "ekman_scores": "emotion_data.ekman_scores",
                        "context_summary": "topic_summary.summary"
                    },
                    "output_key": "persona_data"
                },
                {
                    "skill": "portrait",
                    "operation": "generate",
                    "inputs": {
                        "user_id": "user_id",
                        "common_settings": "context.portrait_settings",
                        "history": "history",
                        "persona_id": "persona_data.selected_personality"
                    },
                    "output_key": "portrait_data"
                },
                {
                    "skill": "persona",
                    "operation": "build_system_prompt",
                    "inputs": {
                        "persona_id": "persona_data.selected_personality"
                    },
                    "params": {
                        "core_system_prompt": "You are Daisy, a friendly AI assistant."
                    },
                    "output_key": "system_prompt_data"
                },
                {
                    "skill": "generation",
                    "operation": "chat",
                    "inputs": {
                        "user_input": "user_input",
                        "system_prompt": "system_prompt_data.system_prompt",
                        "emotion": "emotion_data",
                        "topic_summary": "topic_summary",
                        "memories": "memory_results.memories",
                        "portrait": "portrait_data",
                        "history": "history"
                    },
                    "output_key": "response"
                }
            ]
        },
        "DEEP": {
            "type": "chain",
            "steps": [
                {
                    "type": "parallel",
                    "tasks": [
                        {
                            "skill": "emotion",
                            "operation": "analyze",
                            "inputs": {
                                "text": "user_input",
                                "user_id": "user_id",
                                "session_id": "session_id",
                                "language_hint": "language_hint",
                                "context_history": "history"
                            },
                            "output_key": "emotion_data"
                        },
                        {
                            "skill": "topic",
                            "operation": "summarize",
                            "inputs": {
                                "history": "history",
                                "latest_message": "latest_message",
                                "session_id": "session_id",
                                "language_hint": "language_hint"
                            },
                            "params": {
                                "max_tokens": 120
                            },
                            "output_key": "topic_summary"
                        },
                        {
                            "skill": "reflexion",
                            "operation": "retrieve_exemplars",
                            "inputs": {
                                "query_text": "user_input",
                                "user_id": "user_id"
                            },
                            "output_key": "retrieved_context"
                        }
                    ]
                },
                {
                    "skill": "memory",
                    "operation": "search",
                    "inputs": {
                        "query": "user_input",
                        "user_id": "user_id",
                        "session_id": "session_id",
                        "topic_summary": "topic_summary.summary"
                    },
                    "params": {
                        "limit": 5
                    },
                    "output_key": "memory_results"
                },
                {
                    "skill": "persona",
                    "operation": "select",
                    "inputs": {
                        "user_id": "user_id",
                        "emotion_scores": "emotion_data.scores",
                        "ekman_scores": "emotion_data.ekman_scores",
                        "context_summary": "topic_summary.summary"
                    },
                    "output_key": "persona_data"
                },
                {
                    "skill": "portrait",
                    "operation": "generate",
                    "inputs": {
                        "user_id": "user_id",
                        "common_settings": "context.portrait_settings",
                        "history": "history",
                        "persona_id": "persona_data.selected_personality"
                    },
                    "output_key": "portrait_data"
                },
                {
                    "skill": "persona",
                    "operation": "build_system_prompt",
                    "inputs": {
                        "persona_id": "persona_data.selected_personality"
                    },
                    "params": {
                        "core_system_prompt": "You are Daisy. Use the retrieved context to answer deeply."
                    },
                    "output_key": "system_prompt_data"
                },
                {
                    "skill": "generation",
                    "operation": "chat",
                    "inputs": {
                        "user_input": "user_input",
                        "system_prompt": "system_prompt_data.system_prompt",
                        "emotion": "emotion_data",
                        "topic_summary": "topic_summary",
                        "memories": "memory_results.memories",
                        "portrait": "portrait_data",
                        "retrieved_context": "retrieved_context",
                        "history": "history"
                    },
                    "output_key": "response"
                }
            ]
        }
    },
    "default": {
        "type": "chain",
        "steps": [
            {
                "skill": "generation",
                "operation": "chat",
                "inputs": {
                    "user_input": "user_input",
                    "history": "history",
                    "context": "context"
                },
                "params": {
                    "system_prompt": "I am not sure how to respond to that."
                },
                "output_key": "response"
            }
        ]
    }
}
