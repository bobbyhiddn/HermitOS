#!/bin/bash
# HermitOS Installer ISO Builder
# Builds a bootable Debian 13 (Trixie) live ISO using live-build.
# Must run as root (or with sudo).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR"
WIZARD_SRC="$SCRIPT_DIR/wizard"
WIZARD_DST="$SCRIPT_DIR/config/includes.chroot/opt/hermit-installer/wizard"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[build]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
die()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

# ── Prerequisite checks ──────────────────────────────────────────────────────

check_root() {
    if [[ $EUID -ne 0 ]]; then
        die "This script must run as root. Try: sudo ./build.sh"
    fi
}

check_deps() {
    log "Checking dependencies..."
    local missing=()

    for cmd in lb debootstrap; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        warn "Missing packages: ${missing[*]}"
        log "Installing missing packages..."
        apt-get update -qq
        apt-get install -y live-build debootstrap
    fi

    ok "Dependencies satisfied."
}

# ── Pre-build steps ───────────────────────────────────────────────────────────

copy_wizard() {
    log "Copying wizard source into live image overlay..."
    rm -rf "$WIZARD_DST"
    mkdir -p "$WIZARD_DST"
    cp -r "$WIZARD_SRC/"* "$WIZARD_DST/"
    ok "Wizard copied to: $WIZARD_DST"
}

create_launcher() {
    log "Creating wizard launcher script..."
    local launcher="$SCRIPT_DIR/config/includes.chroot/usr/local/bin/hermit-install"
    cat > "$launcher" << 'LAUNCHER'
#!/bin/bash
# HermitOS installer launcher
# Runs as the hermit-installer user, launches the wizard TUI as root

cd /opt/hermit-installer/wizard
exec sudo /usr/bin/python3 /opt/hermit-installer/wizard/main.py
LAUNCHER
    chmod 755 "$launcher"
    ok "Launcher created: /usr/local/bin/hermit-install"
}

create_systemd_autologin_service() {
    log "Creating systemd autologin override for tty1..."
    local dir="$SCRIPT_DIR/config/includes.chroot/etc/systemd/system/getty@tty1.service.d"
    mkdir -p "$dir"
    cat > "$dir/autologin.conf" << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin hermit-installer --noclear %I $TERM
Type=idle
EOF
    ok "Autologin override written."
}

create_profile_launcher() {
    log "Creating .profile auto-launch for hermit-installer user..."
    local skel="$SCRIPT_DIR/config/includes.chroot/etc/skel"
    # Note: we create the user in a hook; the .profile is set there.
    # But also write to skel as fallback.
    mkdir -p "$skel"
    cat > "$skel/.profile" << 'PROFILE'
# HermitOS live session auto-launcher
if [ "$(tty)" = "/dev/tty1" ] && [ "$USER" = "hermit-installer" ]; then
    clear
    hermit-install
fi
PROFILE
    ok ".profile launcher written to skel."
}

create_live_config() {
    log "Writing live-build config..."
    # Create the auto/config directory
    mkdir -p "$BUILD_DIR/auto"
    ok "live-build auto/config is ready."
}

# ── Build ─────────────────────────────────────────────────────────────────────

run_build() {
    log "Changing to build directory: $BUILD_DIR"
    cd "$BUILD_DIR"

    # Purge ALL cached layers (including chroot) so includes.chroot is re-applied.
    # Plain "lb clean" keeps the chroot cache — overlay changes get silently skipped.
    log "Purging previous build (lb clean --purge)..."
    lb clean --purge 2>/dev/null || true
    ok "Purge complete — full rebuild will run."

    # Run lb config
    log "Running: lb config..."
    bash auto/config
    ok "lb config complete."

    # Build!
    log "Running: lb build (this will take 20-40 minutes)..."
    log "The build downloads ~500MB from Debian mirrors."
    lb build 2>&1 | tee /tmp/hermit-lb-build.log
    local rc=${PIPESTATUS[0]}

    if [[ $rc -ne 0 ]]; then
        die "lb build failed (exit code $rc). See /tmp/hermit-lb-build.log"
    fi

    ok "Build complete!"
}

find_iso() {
    local iso
    iso=$(find "$BUILD_DIR" -maxdepth 1 -name "*.iso" | head -1)
    if [[ -z "$iso" ]]; then
        die "No ISO found in $BUILD_DIR after build."
    fi
    echo "$iso"
}

# ── Post-build ────────────────────────────────────────────────────────────────

show_summary() {
    local iso="$1"
    local size
    size=$(du -sh "$iso" | cut -f1)

    echo ""
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  HermitOS Installer ISO Built Successfully!${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo ""
    echo "  ISO:  $iso"
    echo "  Size: $size"
    echo ""
    echo "  Write to USB with:"
    echo -e "  ${CYAN}sudo dd if=$iso of=/dev/sdX bs=4M status=progress conv=fsync${NC}"
    echo ""
    echo "  Or test in QEMU:"
    echo -e "  ${CYAN}qemu-system-x86_64 -m 2G -cdrom $iso -boot d -enable-kvm${NC}"
    echo ""
    echo "  Or test in Incus:"
    echo -e "  ${CYAN}incus launch images:void/glibc/amd64 testvm --vm${NC}"
    echo -e "  ${CYAN}incus config device add testvm iso disk source=$iso boot.priority=10${NC}"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    echo ""
    echo -e "${CYAN}HermitOS Installer Builder${NC}"
    echo "──────────────────────────────────────────────────"
    echo ""

    check_root
    check_deps
    copy_wizard
    create_launcher
    create_systemd_autologin_service
    create_profile_launcher
    create_live_config
    run_build

    local iso
    iso=$(find_iso)
    show_summary "$iso"
}

main "$@"
