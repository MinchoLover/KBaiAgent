from typing import Dict

from prompt import (
    build_system_prompt,
    build_user_prompt,
    get_prompt_version,
)


def build_prompt_bundle(
    company_role: str,
    company_country: str,
) -> Dict[str, str]:
    return {
        "system": build_system_prompt(),
        "user": build_user_prompt(company_role, company_country),
        "version": get_prompt_version(),
    }
