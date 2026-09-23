"""Custom allauth adapter for Sign in with Apple.

Handles username auto-generation and Apple-specific user creation logic.
"""

import uuid

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AppleSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Adapter to customise how Apple social accounts are created.

    - Auto-generates a unique username based on Apple's ``sub`` identifier.
    - Saves the Apple ``sub`` to ``CustomUser.apple_user_id`` for quick reference.
    - Gracefully handles the case where Apple hides the user's real email.
    """

    def populate_user(self, request, sociallogin, data):
        """Populate user fields from social account data."""
        user = super().populate_user(request, sociallogin, data)

        # Apple returns a unique `sub` (subject) claim per user.
        apple_uid = sociallogin.account.uid or ""

        # Auto-generate username if missing (Apple doesn't provide one).
        if not user.username:
            # Create a readable but unique username: apple_<short-hash>
            short_id = uuid.uuid4().hex[:8]
            user.username = f"apple_{short_id}"

        # Store Apple user ID for reference.
        if apple_uid:
            user.apple_user_id = apple_uid

        # Apple may return first/last name only on the very first auth.
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name

        return user

    def save_user(self, request, sociallogin, form=None):
        """Save the new user and persist the Apple user ID."""
        user = super().save_user(request, sociallogin, form)

        apple_uid = sociallogin.account.uid or ""
        if apple_uid and not user.apple_user_id:
            user.apple_user_id = apple_uid
            user.save(update_fields=["apple_user_id"])

        return user
