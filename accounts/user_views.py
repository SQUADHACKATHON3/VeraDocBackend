from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.serializers import ChangePasswordSerializer
from common.security import hash_password, verify_password


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    user = request.user

    if not user.password_hash:
        return Response(
            {
                "detail": "This account uses Google sign-in. Set a password via forgot-password if needed."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not verify_password(data["currentPassword"], user.password_hash):
        return Response({"detail": "Current password is incorrect"}, status=status.HTTP_401_UNAUTHORIZED)

    user.password_hash = hash_password(data["newPassword"])
    user.save(update_fields=["password_hash"])
    return Response({"message": "Password updated successfully"})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_account(request):
    request.user.delete()
    return Response({"message": "Account deleted"})
