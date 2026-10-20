# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0

.PHONY: install test lint fmt type build serve check openapi docker clean

UV ?= uv
NPM ?= npm

install:
	$(UV) sync --extra dev
	cd web && $(NPM) ci

build:
	@test -d web/node_modules || (cd web && $(NPM) ci)
	cd web && $(NPM) run build

test: build
	$(UV) run pytest
	cd web && $(NPM) test

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	cd web && $(NPM) run typecheck

fmt:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

type:
	$(UV) run mypy

serve: build
	$(UV) run senseai-studio serve

check:
	$(UV) run senseai-studio check

openapi:
	$(UV) run senseai-studio openapi > docs/openapi.json

docker:
	docker build -t senseai-studio .

clean:
	rm -rf data src/senseai_studio/static .coverage .pytest_cache .mypy_cache .ruff_cache
