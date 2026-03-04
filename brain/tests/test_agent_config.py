"""Tests for engineering_brain.agent.config — AgentConfig facade."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from engineering_brain.agent.config import AgentConfig, get_agent_config
from engineering_brain.core.config import BrainConfig


class TestAgentConfig:
    def test_is_configured_true(self):
        cfg = AgentConfig(
            enabled=True,
            api_key="sk-ant-xxx",
            model="m",
            orchestrator_model="m",
            max_workers=3,
            max_tokens=4096,
            timeout=60,
            cards_dir="",
        )
        assert cfg.is_configured is True

    def test_is_configured_no_key(self):
        cfg = AgentConfig(
            enabled=True,
            api_key="",
            model="m",
            orchestrator_model="m",
            max_workers=3,
            max_tokens=4096,
            timeout=60,
            cards_dir="",
        )
        assert cfg.is_configured is False

    def test_is_configured_disabled(self):
        cfg = AgentConfig(
            enabled=False,
            api_key="sk-ant-xxx",
            model="m",
            orchestrator_model="m",
            max_workers=3,
            max_tokens=4096,
            timeout=60,
            cards_dir="",
        )
        assert cfg.is_configured is False

    def test_frozen(self):
        cfg = AgentConfig(
            enabled=True,
            api_key="x",
            model="m",
            orchestrator_model="m",
            max_workers=3,
            max_tokens=4096,
            timeout=60,
            cards_dir="",
        )
        with pytest.raises(Exception):
            cfg.enabled = False  # type: ignore[misc]


class TestGetAgentConfig:
    def test_from_brain_config_defaults(self):
        brain_cfg = BrainConfig()
        agent_cfg = get_agent_config(brain_cfg)
        assert agent_cfg.enabled is False
        assert agent_cfg.api_key == ""
        assert agent_cfg.max_workers == 3

    def test_from_env(self):
        env = {
            "BRAIN_AGENT_ENABLED": "true",
            "BRAIN_AGENT_API_KEY": "sk-test-123",
            "BRAIN_AGENT_MAX_WORKERS": "5",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            brain_cfg = BrainConfig()
            agent_cfg = get_agent_config(brain_cfg)
            assert agent_cfg.enabled is True
            assert agent_cfg.api_key == "sk-test-123"
            assert agent_cfg.max_workers == 5

    def test_model_defaults(self):
        brain_cfg = BrainConfig()
        agent_cfg = get_agent_config(brain_cfg)
        assert "opus" in agent_cfg.model.lower() or "claude" in agent_cfg.model.lower()

    def test_custom_cards_dir(self):
        env = {"BRAIN_AGENT_CARDS_DIR": "/custom/cards"}
        with mock.patch.dict(os.environ, env, clear=False):
            brain_cfg = BrainConfig()
            agent_cfg = get_agent_config(brain_cfg)
            assert agent_cfg.cards_dir == "/custom/cards"
