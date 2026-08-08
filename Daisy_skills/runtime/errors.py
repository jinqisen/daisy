class SkillNotFoundError(Exception):
    pass

class SkillExecutionError(Exception):
    pass

class SkillValidationError(Exception):
    pass

class SkillTimeoutError(Exception):
    pass

class SkillResourceError(Exception):
    pass

class SkillDependencyError(Exception):
    pass
