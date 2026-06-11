from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Map DRF errors to FastAPI-compatible `{ "detail": ... }` responses."""
    response = exception_handler(exc, context)
    if response is not None:
        data = response.data
        if isinstance(data, dict):
            if "detail" not in data:
                if "non_field_errors" in data:
                    response.data = {"detail": data["non_field_errors"][0]}
                elif len(data) == 1:
                    key = next(iter(data))
                    val = data[key]
                    if isinstance(val, list):
                        response.data = {"detail": val[0]}
                    else:
                        response.data = {"detail": val}
                else:
                    response.data = {"detail": data}
        return response

    if settings.DEBUG:
        return Response(
            {"error": "Internal server error", "detail": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
