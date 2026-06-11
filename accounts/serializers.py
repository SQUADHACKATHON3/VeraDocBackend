from rest_framework import serializers


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=200)
    organisation = serializers.CharField(min_length=1, max_length=200)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=200, write_only=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=1, max_length=200, write_only=True)


class TokenSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField(default="bearer")


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    organisation = serializers.CharField()
    email = serializers.EmailField()
    credits = serializers.IntegerField()
    emailVerified = serializers.BooleanField(source="email_verified")


class VerifyEmailSerializer(serializers.Serializer):
    otp = serializers.RegexField(regex=r"^\d{6}$", min_length=6, max_length=6)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(regex=r"^\d{6}$", min_length=6, max_length=6)
    newPassword = serializers.CharField(min_length=8, max_length=200)


class ChangePasswordSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(min_length=1, max_length=200)
    newPassword = serializers.CharField(min_length=8, max_length=200)
