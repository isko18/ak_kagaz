# serializers.py
from rest_framework import serializers

from .models import StaticPage, News


class StaticPageSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = StaticPage
        fields = (
            "id",
            "key",
            "title",
            "slug",
            "logo",
            "logo_url",
            "content",
            "address",
            "phone",
            "email",
            "map_iframe",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def get_logo_url(self, obj):
        request = self.context.get("request")
        if obj.logo and getattr(obj.logo, "url", None):
            url = obj.logo.url
            return request.build_absolute_uri(url) if request else url
        return None


class NewsListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = News
        fields = (
            "id",
            "title",
            "slug",
            "preview_text",
            "image",
            "image_url",
            "is_published",
            "published_at",
        )

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and getattr(obj.image, "url", None):
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return None


class NewsDetailSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = News
        fields = (
            "id",
            "title",
            "slug",
            "preview_text",
            "content",
            "image",
            "image_url",
            "is_published",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and getattr(obj.image, "url", None):
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return None
