.PHONY: help  # List phony targets
help:
	@cat "Makefile" | grep '^.PHONY:' | sed -e "s/^.PHONY:/- make/"

.PHONY: start  # Start application
start:
	uv run --prerelease=allow --group dev streamlit run src/main.py

.PHONY: test  # Run tests
test:
	uv run --prerelease=allow --group test pytest src/tests

.PHONY: clean  # Clean development environment
clean:
	rm -rf .venv

.PHONY: start-docker  # Start application in Docker
start-docker:
	docker build -t streamlit-playground .
	docker run -p 8501:8501 streamlit-playground

.PHONY: buildah  # Buil image using buildah and start application in Docker
buildah:
	buildah build -t streamlit-playground:dev .
	docker run -p 8501:8501 localhost/streamlit-playground:dev