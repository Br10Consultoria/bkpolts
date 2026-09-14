"""Detecção de erros retornados pelas CLIs dos equipamentos."""

import re


def datacom_tftp_failure_reason(response: str) -> str | None:
    if not re.search(r"(?i)(upload transfer failed|transfer failed|\berror(?:s)?\s*:|timed?\s*out)", response):
        return None
    return next(
        (line.strip() for line in response.splitlines()
         if re.search(r"(?i)(failed|error|timed?\s*out)", line)),
        "A OLT recusou ou não conseguiu concluir o envio TFTP",
    )
