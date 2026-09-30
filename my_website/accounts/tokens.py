from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """会員登録時のメール認証リンク用トークン。

    is_active をハッシュに含めるため、認証（有効化）が済んだ時点で同じリンクは使えなくなる。
    有効期限は PASSWORD_RESET_TIMEOUT（既定 3 日）に従う。
    """

    key_salt = 'accounts.tokens.EmailVerificationTokenGenerator'

    def _make_hash_value(self, user, timestamp):
        return f'{user.pk}{user.password}{user.is_active}{timestamp}{user.email}'


email_verification_token = EmailVerificationTokenGenerator()
