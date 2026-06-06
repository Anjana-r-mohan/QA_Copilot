"""Property-based tests for the PatternAnalyzer module.

Feature: bitbucket-pr-test-generator, Property 5: Code Pattern Detection
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from models import FileChange, FileChangeType, PatternType
from pr_test_generator.pattern_analyzer import PatternAnalyzer


# --- Strategies ---

# Concrete code examples for each pattern type that match the PatternAnalyzer regexes.
_navigation_examples = st.sampled_from([
    'navigate(route)',
    'navigate("home")',
    'pushViewController(vc, animated: true)',
    'NavHost(navController = navController)',
])

_api_examples = st.sampled_from([
    '@GET("/endpoint")',
    '@POST("/users")',
    'HttpClient(engine)',
])

_state_examples = st.sampled_from([
    'val flow: StateFlow<Int> = _flow',
    'val state: MutableState<Boolean> = mutableStateOf(false)',
    '@Published var name: String = ""',
    'val count = remember { mutableStateOf(0) }',
])

_input_examples = st.sampled_from([
    'onClick { doSomething() }',
    'onValueChange = { newValue -> update(newValue) }',
    'addTarget(self, action: #selector(buttonTapped))',
])

# Map pattern type to its corresponding code examples strategy
_pattern_type_to_examples = {
    PatternType.NAVIGATION: _navigation_examples,
    PatternType.API_CALL: _api_examples,
    PatternType.STATE_MANAGEMENT: _state_examples,
    PatternType.USER_INPUT: _input_examples,
}

# Strategy for random surrounding code lines (to ensure pattern is detected in context)
_surrounding_code_line = st.sampled_from([
    'import kotlin.collections.*',
    'class MyViewModel {',
    '    val x = 42',
    '    fun doWork() {',
    '        println("hello")',
    '    }',
    '}',
    '// This is a comment',
    'private val logger = Logger.getLogger()',
    'data class Item(val id: Int, val name: String)',
    'override fun onCreate(savedInstanceState: Bundle?) {',
    '    super.onCreate(savedInstanceState)',
    'companion object {',
    '    const val TAG = "MyClass"',
])


@st.composite
def pattern_type_with_surrounded_code(draw):
    """Generate a (PatternType, code_string) pair where the pattern is wrapped
    in random surrounding code lines to ensure detection works in context."""
    pattern_type = draw(st.sampled_from(list(PatternType)))
    code_snippet = draw(_pattern_type_to_examples[pattern_type])

    # Generate random surrounding code: 0-5 lines before and 0-5 after
    prefix_lines = draw(st.lists(_surrounding_code_line, min_size=0, max_size=5))
    suffix_lines = draw(st.lists(_surrounding_code_line, min_size=0, max_size=5))

    # Build full code string with surrounding context
    all_lines = prefix_lines + [code_snippet] + suffix_lines
    full_code = "\n".join(all_lines)

    return pattern_type, full_code


# --- Property 5: Code Pattern Detection ---


class TestCodePatternDetection:
    """Property 5: Code Pattern Detection.

    For any pattern type (navigation, API call, state management, user input)
    and any code string containing a matching pattern, scanning the code should
    detect at least one pattern of the expected type with a non-empty description.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    """

    @given(data=pattern_type_with_surrounded_code())
    @settings(max_examples=100)
    def test_matching_code_detected_with_correct_type(self, data: tuple):
        """For any pattern type and code containing a matching pattern,
        the PatternAnalyzer should detect at least one pattern of that type.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        pattern_type, code_string = data

        # Create a FileChange with the code as head_content and empty base_content
        # so patterns appear as "added"
        file_change = FileChange(
            path="test_file.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content=code_string,
        )

        analyzer = PatternAnalyzer()
        results = analyzer.analyze(file_change)

        # At least one pattern should be detected
        assert len(results) > 0, (
            f"Expected at least one detected pattern for type '{pattern_type.value}' "
            f"with code:\n{code_string!r}"
        )

        # At least one result should match the expected pattern type
        matching = [r for r in results if r.pattern_type == pattern_type]
        assert len(matching) > 0, (
            f"Expected at least one pattern of type '{pattern_type.value}', "
            f"but got types: {[r.pattern_type.value for r in results]} "
            f"for code:\n{code_string!r}"
        )

    @given(data=pattern_type_with_surrounded_code())
    @settings(max_examples=100)
    def test_detected_patterns_have_non_empty_description(self, data: tuple):
        """For any detected pattern, the description field must be non-empty.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        pattern_type, code_string = data

        file_change = FileChange(
            path="test_file.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content=code_string,
        )

        analyzer = PatternAnalyzer()
        results = analyzer.analyze(file_change)

        # All detected patterns should have non-empty descriptions
        for result in results:
            assert result.description, (
                f"Detected pattern of type '{result.pattern_type.value}' "
                f"has empty description for code:\n{code_string!r}"
            )
            assert len(result.description.strip()) > 0, (
                f"Detected pattern description is whitespace-only "
                f"for type '{result.pattern_type.value}'"
            )
