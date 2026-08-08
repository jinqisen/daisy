from enum import Enum

class EmotionalStrategy(str, Enum):
    """
    EvoEmo 情感策略枚举
    用于指导 Agent 在不同情境下选择最优的应对方式
    """
    EMPATHETIC_SUPPORT = "Empathetic_Support"        # 共情支持：常规安慰，建立安全感
    PLAYFUL_TEASING = "Playful_Teasing"              # 玩笑挑逗：增加情趣，活跃气氛
    CONSTRUCTIVE_CHALLENGE = "Constructive_Challenge" # 建设性挑战：激将法，打破消极循环
    EMOTIONAL_MIRRORING = "Emotional_Mirroring"      # 情绪镜像：完全同步，表示理解
    STRATEGIC_WITHDRAWAL = "Strategic_Withdrawal"    # 策略性撤退：冷处理，避免冲突升级
    DIRECT_ADVICE = "Direct_Advice"                  # 直接建议：跳过情绪，直奔解决问题

    @classmethod
    def get_description(cls, strategy: str) -> str:
        descriptions = {
            cls.EMPATHETIC_SUPPORT: "提供温暖的共情和支持，优先照顾用户情绪，建立安全感。",
            cls.PLAYFUL_TEASING: "使用幽默、调侃或轻微的冒犯来活跃气氛，拉近距离。",
            cls.CONSTRUCTIVE_CHALLENGE: "指出用户思维盲区或使用激将法，打破消极循环，促进行动。",
            cls.EMOTIONAL_MIRRORING: "完全同步用户的情绪强度和语调，让用户感到被深度理解。",
            cls.STRATEGIC_WITHDRAWAL: "暂时降低热情或延迟回应，给予空间，避免冲突升级。",
            cls.DIRECT_ADVICE: "跳过过多的情感铺垫，直接提供理性、具体的解决方案。"
        }
        return descriptions.get(strategy, "无描述")
