"""Tests for anthropic_credentials module."""


class TestParseEnvFile:
    """Test .env file parsing."""

    def test_parse_simple_values(self, tmp_path):
        """Test parsing simple KEY=value pairs."""
        from anthropic_credentials import parse_env_file

        env_file = tmp_path / "test.env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n")

        result = parse_env_file(env_file)

        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_parse_quoted_values(self, tmp_path):
        """Test parsing quoted values."""
        from anthropic_credentials import parse_env_file

        env_file = tmp_path / "test.env"
        env_file.write_text("KEY1=\"quoted value\"\nKEY2='single quoted'\n")

        result = parse_env_file(env_file)

        assert result == {"KEY1": "quoted value", "KEY2": "single quoted"}

    def test_skip_comments_and_empty_lines(self, tmp_path):
        """Test that comments and empty lines are skipped."""
        from anthropic_credentials import parse_env_file

        env_file = tmp_path / "test.env"
        env_file.write_text("# Comment\nKEY1=value1\n\n# Another comment\nKEY2=value2\n")

        result = parse_env_file(env_file)

        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_handle_missing_file(self, tmp_path):
        """Test handling of missing file."""
        from anthropic_credentials import parse_env_file

        result = parse_env_file(tmp_path / "nonexistent.env")

        assert result == {}


class TestLoadAnthropicCredential:
    """Test credential loading."""

    def test_load_api_key(self, tmp_path, monkeypatch):
        """Test loading API key from secrets file."""
        import anthropic_credentials

        env_file = tmp_path / "secrets.env"
        env_file.write_text(
            "ANTHROPIC_API_KEY=sk-ant-api03-test-key-with-enough-length-to-pass-validation-12345678901234567890\n"
        )

        monkeypatch.setattr(anthropic_credentials, "SECRETS_PATH", env_file)

        credential = anthropic_credentials.load_anthropic_credential()

        assert credential is not None
        assert credential.header_name == "x-api-key"
        assert (
            credential.header_value
            == "sk-ant-api03-test-key-with-enough-length-to-pass-validation-12345678901234567890"
        )

    def test_load_oauth_token(self, tmp_path, monkeypatch):
        """Test loading OAuth token from secrets file."""
        import anthropic_credentials

        env_file = tmp_path / "secrets.env"
        env_file.write_text("ANTHROPIC_OAUTH_TOKEN=test-oauth-token-12345\n")

        monkeypatch.setattr(anthropic_credentials, "SECRETS_PATH", env_file)

        credential = anthropic_credentials.load_anthropic_credential()

        assert credential is not None
        assert credential.header_name == "Authorization"
        assert credential.header_value == "Bearer test-oauth-token-12345"

    def test_oauth_takes_precedence(self, tmp_path, monkeypatch):
        """Test that OAuth token takes precedence over API key."""
        import anthropic_credentials

        env_file = tmp_path / "secrets.env"
        env_file.write_text(
            "ANTHROPIC_API_KEY=sk-ant-api03-key\nANTHROPIC_OAUTH_TOKEN=oauth-token-12345\n"
        )

        monkeypatch.setattr(anthropic_credentials, "SECRETS_PATH", env_file)

        credential = anthropic_credentials.load_anthropic_credential()

        assert credential is not None
        assert credential.header_name == "Authorization"
        assert "oauth-token-12345" in credential.header_value

    def test_missing_file_returns_none(self, tmp_path, monkeypatch):
        """Test that missing secrets file returns None."""
        import anthropic_credentials

        monkeypatch.setattr(anthropic_credentials, "SECRETS_PATH", tmp_path / "nonexistent.env")

        credential = anthropic_credentials.load_anthropic_credential()

        assert credential is None


class TestValidateCredentialFormat:
    """Test credential format validation."""

    def test_valid_api_key(self):
        """Test validation of valid API key."""
        from anthropic_credentials import AnthropicCredential, validate_credential_format

        credential = AnthropicCredential(
            header_name="x-api-key",
            header_value="sk-ant-api03-" + "x" * 50,
        )

        is_valid, error = validate_credential_format(credential)

        assert is_valid
        assert error == ""

    def test_invalid_api_key_prefix(self):
        """Test validation rejects wrong API key prefix."""
        from anthropic_credentials import AnthropicCredential, validate_credential_format

        credential = AnthropicCredential(
            header_name="x-api-key",
            header_value="wrong-prefix-key",
        )

        is_valid, error = validate_credential_format(credential)

        assert not is_valid
        assert "sk-ant-" in error

    def test_valid_oauth_token(self):
        """Test validation of valid OAuth token."""
        from anthropic_credentials import AnthropicCredential, validate_credential_format

        credential = AnthropicCredential(
            header_name="Authorization",
            header_value="Bearer " + "x" * 30,
        )

        is_valid, error = validate_credential_format(credential)

        assert is_valid
        assert error == ""

    def test_oauth_token_missing_bearer(self):
        """Test validation rejects OAuth without Bearer prefix."""
        from anthropic_credentials import AnthropicCredential, validate_credential_format

        credential = AnthropicCredential(
            header_name="Authorization",
            header_value="token-without-bearer",
        )

        is_valid, error = validate_credential_format(credential)

        assert not is_valid
        assert "Bearer" in error
