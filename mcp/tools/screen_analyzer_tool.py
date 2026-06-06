class ScreenAnalyzerTool:

    def analyze(
        self,
        elements
    ):

        clickable = []
        inputs = []
        labels = []

        for element in elements:

            if element.get("clickable"):

                clickable.append(element)

            if element.get("class_name", "").endswith(
                "EditText"
            ):

                inputs.append(element)

            if element.get("text"):

                labels.append(element)

        return {

            "total_elements": len(elements),

            "clickable_elements": clickable,

            "input_fields": inputs,

            "labels": labels
        }