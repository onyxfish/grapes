"""Tests for ID and ARN utility functions."""

from grapes.utils.ids import extract_task_definition_name, sanitize_metric_id


class TestExtractTaskDefinitionName:
    """Tests for extract_task_definition_name function."""

    def test_full_arn(self):
        """Test extraction from a full ARN."""
        arn = "arn:aws:ecs:us-east-1:123456789:task-definition/my-task:5"
        assert extract_task_definition_name(arn) == "my-task:5"

    def test_arn_without_revision(self):
        """Test extraction from ARN without revision."""
        arn = "arn:aws:ecs:us-east-1:123456789:task-definition/my-task"
        assert extract_task_definition_name(arn) == "my-task"

    def test_simple_name(self):
        """Test with just a task definition name (no ARN)."""
        name = "my-task:5"
        assert extract_task_definition_name(name) == "my-task:5"

    def test_empty_string(self):
        """Test with empty string."""
        assert extract_task_definition_name("") == ""

    def test_name_with_hyphens(self):
        """Test with task name containing hyphens."""
        arn = "arn:aws:ecs:us-east-1:123456789:task-definition/my-complex-task-name:123"
        assert extract_task_definition_name(arn) == "my-complex-task-name:123"


class TestSanitizeMetricId:
    """Tests for sanitize_metric_id function."""

    def test_simple_name(self):
        """Test with a simple alphanumeric name."""
        assert sanitize_metric_id("myservice") == "myservice"

    def test_name_with_hyphens(self):
        """Test that hyphens are replaced with underscores."""
        assert sanitize_metric_id("my-service") == "my_service"

    def test_name_with_dots(self):
        """Test that dots are replaced with underscores."""
        assert sanitize_metric_id("my.service") == "my_service"

    def test_uppercase_conversion(self):
        """Test that uppercase is converted to lowercase."""
        assert sanitize_metric_id("MyService") == "myservice"

    def test_starts_with_number(self):
        """Test that names starting with numbers get prefix."""
        assert sanitize_metric_id("123service") == "m_123service"

    def test_complex_name(self):
        """Test with a complex name containing multiple special chars."""
        result = sanitize_metric_id("My-Service.Name:v1")
        assert result == "my_service_name_v1"

    def test_empty_string(self):
        """Test with empty string."""
        assert sanitize_metric_id("") == ""

    def test_all_special_chars(self):
        """Test with all special characters."""
        result = sanitize_metric_id("!@#$%")
        assert result == "m______"  # Starts with non-alpha, gets prefix
