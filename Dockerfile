FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AGENT_REACH_DISCOVERY_DB=/data/discovery.db

WORKDIR /app
COPY pyproject.toml README.md ./
COPY agent_reach ./agent_reach
COPY skills ./skills
RUN pip install . && useradd --create-home reach && mkdir /data && chown reach /data
USER reach
VOLUME ["/data"]

# stdio MCP server by default. Use: docker run -i --rm -v reach-data:/data leads-licker mcp
ENTRYPOINT ["leads-licker"]
CMD ["mcp"]
