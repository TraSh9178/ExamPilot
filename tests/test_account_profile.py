"""Image validation and account isolation for session-only avatars."""

from io import BytesIO
import time

from PIL import Image, ImageOps, PngImagePlugin
import pytest

from services.account_profile import (
    AVATAR_STATE_KEY,
    MAX_AVATAR_BYTES,
    get_account_avatar,
    remove_account_avatar,
    save_account_avatar,
)
from services.auth_service import AuthUser
from services.auth_session import logout_session, start_authenticated_session


USER_A = AuthUser("57ef2d19-a4a2-49eb-99c6-506bafac514a", "alice")
USER_B = AuthUser("147dfb7d-debb-41ac-93bb-24b764b55a3a", "bob")


def _session(user=USER_A):
    state = {}
    start_authenticated_session(state, user)
    return state


def _image(image_format="PNG", size=(640, 480), *, metadata=False):
    output = BytesIO()
    image = Image.new("RGB", size, (76, 102, 145))
    options = {}
    if metadata and image_format == "PNG":
        info = PngImagePlugin.PngInfo()
        info.add_text("Description", "private filename or location")
        options["pnginfo"] = info
    elif metadata and image_format == "JPEG":
        exif = Image.Exif()
        exif[270] = "private filename or location"
        exif[274] = 6
        options["exif"] = exif
    image.save(output, format=image_format, **options)
    return output.getvalue()


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_avatar_accepts_actual_png_and_jpeg_and_removes_metadata(image_format):
    state = _session()
    result = save_account_avatar(
        state, _image(image_format, metadata=True), expected_user_id=USER_A.user_id,
    )
    assert result.success
    avatar = get_account_avatar(state)
    with Image.open(BytesIO(avatar)) as image:
        assert image.format == "PNG"
        assert max(image.size) == 256
        assert image.size == ((192, 256) if image_format == "JPEG" else (256, 192))
        assert image.info == {}
        assert not image.getexif()


@pytest.mark.parametrize("bad_image", [b"", b"not an image", _image("GIF"), _image("BMP")])
def test_invalid_or_unsupported_images_preserve_the_previous_avatar(bad_image):
    state = _session()
    save_account_avatar(state, _image(), expected_user_id=USER_A.user_id)
    previous = get_account_avatar(state)
    result = save_account_avatar(state, bad_image, expected_user_id=USER_A.user_id)
    assert not result.success
    assert result.error_code == "invalid_image"
    assert get_account_avatar(state) == previous


def test_truncated_image_is_rejected_before_an_avatar_is_saved():
    state = _session()
    image_bytes = _image("JPEG")
    result = save_account_avatar(state, image_bytes[:len(image_bytes) // 2], expected_user_id=USER_A.user_id)
    assert not result.success
    assert get_account_avatar(state) is None


def test_file_size_and_decoded_pixel_limits_are_enforced():
    state = _session()
    too_large = save_account_avatar(
        state, b"x" * (MAX_AVATAR_BYTES + 1), expected_user_id=USER_A.user_id,
    )
    assert not too_large.success
    assert too_large.error_code == "image_too_large"
    too_many_pixels = save_account_avatar(
        state, _image(size=(2001, 2000)), expected_user_id=USER_A.user_id,
    )
    assert not too_many_pixels.success
    assert get_account_avatar(state) is None


def test_avatar_reads_discard_a_different_accounts_image():
    state = _session()
    save_account_avatar(state, _image(), expected_user_id=USER_A.user_id)
    state["auth_user"] = USER_B
    assert get_account_avatar(state) is None
    assert AVATAR_STATE_KEY not in state


def test_previous_account_callback_cannot_replace_or_remove_current_avatar():
    state = _session(USER_B)
    save_account_avatar(state, _image(), expected_user_id=USER_B.user_id)
    current_avatar = get_account_avatar(state)
    save = save_account_avatar(state, _image("JPEG"), expected_user_id=USER_A.user_id)
    remove = remove_account_avatar(state, expected_user_id=USER_A.user_id)
    assert not save.success and save.error_code == "account_changed"
    assert not remove.success and remove.error_code == "account_changed"
    assert get_account_avatar(state) == current_avatar


def test_account_switch_during_decoding_does_not_store_previous_accounts_upload(monkeypatch):
    state = _session()
    original_transpose = ImageOps.exif_transpose

    def switch_account(image):
        start_authenticated_session(state, USER_B)
        return original_transpose(image)

    monkeypatch.setattr(ImageOps, "exif_transpose", switch_account)
    result = save_account_avatar(state, _image(), expected_user_id=USER_A.user_id)
    assert not result.success
    assert result.error_code == "account_changed"
    assert state["auth_user"] == USER_B
    assert get_account_avatar(state) is None


def test_signing_out_and_signing_in_again_does_not_restore_an_avatar():
    state = _session()
    save_account_avatar(state, _image(), expected_user_id=USER_A.user_id)
    logout_session(state)
    assert get_account_avatar(state) is None
    start_authenticated_session(state, USER_A)
    assert get_account_avatar(state) is None


def test_expired_session_clears_avatar_and_rejects_upload_and_removal():
    state = _session()
    save_account_avatar(state, _image(), expected_user_id=USER_A.user_id)
    state["auth_started_at"] = time.time() - 9 * 60 * 60
    assert get_account_avatar(state) is None
    assert state == {}
    save = save_account_avatar(state, _image(), expected_user_id=USER_A.user_id)
    remove = remove_account_avatar(state, expected_user_id=USER_A.user_id)
    assert not save.success and save.error_code == "not_authenticated"
    assert not remove.success and remove.error_code == "not_authenticated"
    assert state == {}


def test_missing_login_clears_an_orphaned_avatar():
    state = _session()
    save_account_avatar(state, _image(), expected_user_id=USER_A.user_id)
    del state["auth_user"]
    assert get_account_avatar(state) is None
    assert AVATAR_STATE_KEY not in state


def test_remove_avatar_leaves_identity_and_learning_state_intact():
    state = _session()
    state["courses"] = ["existing course"]
    save_account_avatar(state, _image(), expected_user_id=USER_A.user_id)
    result = remove_account_avatar(state, expected_user_id=USER_A.user_id)
    assert result.success
    assert get_account_avatar(state) is None
    assert state["auth_user"] == USER_A
    assert state["courses"] == ["existing course"]
