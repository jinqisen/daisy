import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import os
import structlog
from typing import List, Dict, Any
from app.core.constants import (
    PERSONALITY_TYPES, RL_STATE_DIM, RL_ACTION_DIM,
    RL_DOMINANT_THRESHOLD, RL_DOMINANT_TARGET,
    RL_MIXED_MODE_TOP1_THRESHOLD, RL_MIXED_MODE_TOP2_THRESHOLD
)

logger = structlog.get_logger()

# Hyperparameters (only those needed for inference if any, or just keep them)
# LR = 1e-3 # Not needed
# GAMMA = 0.99 # Not needed
# EPS_CLIP = 0.2 # Not needed
# K_EPOCHS = 4 # Not needed

class PolicyNetwork(nn.Module):
    """
    策略网络，用于根据状态生成动作概率分布。
    """
    def __init__(self, state_dim, action_dim):
        super(PolicyNetwork, self).__init__()
        self.fc1 = nn.Linear(state_dim, 64)
        self.fc2 = nn.Linear(64, 64)
        self.fc3 = nn.Linear(64, action_dim)
        
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.softmax(self.fc3(x), dim=-1)
        return x

class RLAgent:
    """
    强化学习代理，负责根据当前状态选择人格策略。
    目前主要用于推理 (Inference)。
    """
    def __init__(self, user_id: str = "default", state_dim=RL_STATE_DIM, action_dim=RL_ACTION_DIM):
        self.user_id = user_id
        self.personalities = PERSONALITY_TYPES
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.policy = PolicyNetwork(state_dim, action_dim)
        # self.optimizer = optim.Adam(self.policy.parameters(), lr=LR) # 推理模式不需要
        # self.memory = [] # 移除
        
        # 用共享常量。原先按"当前文件向上两层"算,而本文件从 app/services/
        # 移到 app/services/learning/ 后层数已经不对 —— 它之所以还能工作纯属巧合
        # (算出来的目录恰好也含 model/)。这类靠数层数的路径会被移动静默改坏。
        from app.core.paths import SERVER_DIR
        server_dir = SERVER_DIR
        
        # 尝试兄弟目录 model 优先
        model_dir = os.path.join(os.path.dirname(server_dir), "model")
        if not os.path.exists(model_dir):
            # 回退到内部 model 目录
            model_dir = os.path.join(server_dir, "model")
        
        # 确保 model 目录存在 (尽管推理通常期望它存在)
        if not os.path.exists(model_dir):
            os.makedirs(model_dir, exist_ok=True)

        self.model_path = os.path.join(model_dir, f"rl_model_{self.user_id}.pth")
        base_model_path = os.path.join(model_dir, "rl_model.pth")
        
        load_path = None
        if os.path.exists(self.model_path):
            load_path = self.model_path
        elif os.path.exists(base_model_path):
            load_path = base_model_path

        if load_path:
            try:
                loaded_state = torch.load(load_path, map_location=torch.device('cpu'))
                # 检查维度是否匹配 (简单检查)
                if loaded_state['fc3.weight'].shape[0] == action_dim:
                    self.policy.load_state_dict(loaded_state)
                    logger.info(f"RL Model loaded from {load_path} for user {self.user_id}.")
                else:
                    logger.warning("RL Model dimension mismatch (likely personality change). Starting fresh.")
            except Exception as e:
                logger.warning(f"Failed to load RL model from {load_path}: {e}, starting fresh.")
        else:
             logger.info("No existing model found. Using random initialization.")

    def select_action(self, state_vector: List[float]) -> Dict[str, Any]:
        """
        输入: 状态向量 (例如，情绪分数，填充至 28 维)
        输出: { "personality": str, "weights": dict, "action_idx": int }
        """
        state = torch.FloatTensor(state_vector).unsqueeze(0)
        with torch.no_grad():
            probs = self.policy(state)
        
        # 根据概率采样动作
        dist = torch.distributions.Categorical(probs)
        action_idx = dist.sample().item()
        
        weights = probs.squeeze(0).tolist()

        # 强制主导人格规则: 最大权重必须 >= 0.6
        # 这确保 AI 总是有一个清晰的主要人格
        # 更新: 如果至少有 2 个显著权重 (> 0.25)，允许混合人格
        
        sorted_indices = np.argsort(weights)[::-1] # 降序
        top1_idx = sorted_indices[0]
        top2_idx = sorted_indices[1]
        
        top1_val = weights[top1_idx]
        top2_val = weights[top2_idx]
        
        # 如果前 2 个都显著，我们允许 "混合模式"，而不强制 0.65 的主导地位
        is_mixed_mode = (top1_val > RL_MIXED_MODE_TOP1_THRESHOLD and top2_val > RL_MIXED_MODE_TOP2_THRESHOLD)
        
        if not is_mixed_mode:
            max_val = max(weights)
            if max_val < RL_DOMINANT_THRESHOLD:
                # logger.info(f"Boosting dominant personality. Max was {max_val:.2f}")
                max_idx = weights.index(max_val)
                target_max = RL_DOMINANT_TARGET # 提升至 65% 以使其明显主导
                remaining_prob = 1.0 - target_max
                sum_others = sum(weights) - max_val
                
                new_weights = []
                for i, w in enumerate(weights):
                    if i == max_idx:
                        new_weights.append(target_max)
                    else:
                        # 按比例缩放其他权重
                        if sum_others > 0:
                            new_weights.append(w * (remaining_prob / sum_others))
                        else:
                            # 如果其他权重为 0，则回退
                            new_weights.append(remaining_prob / (len(weights) - 1))
                weights = new_weights
        else:
            pass
            # logger.info(f"Mixed Personality Mode detected: Top1={top1_val:.2f}, Top2={top2_val:.2f}. No boosting applied.")
        
        # 额外的安全检查: 确保没有负权重且和为 1.0
        weights = [max(0.0, w) for w in weights]
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]
        
        personality_weights = {self.personalities[i]: weights[i] for i in range(len(self.personalities))}
        
        return {
            "personality": self.personalities[action_idx],
            "weights": personality_weights,
            "action_idx": action_idx,
            "prob_tensor": probs # 用于日志/调试
        }

    # 移除了 store_transition 和 update (推理专用代理)

# 缓存用户特定的代理
_agents_cache: Dict[str, RLAgent] = {}

def get_rl_agent(user_id: str = "default") -> RLAgent:
    if user_id not in _agents_cache:
        _agents_cache[user_id] = RLAgent(user_id=user_id)
    return _agents_cache[user_id]
