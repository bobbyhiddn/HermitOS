# HermitOS Installer

A bootable live ISO built with Debian's `live-build` tool. Boots into a live Debian 13
(Trixie) environment and auto-launches the HermitOS installation wizard.

## Why live-build (not dd)

The previous approach (dd a VM disk image to USB) kernel-panicked on bare metal because
the VM's initramfs only had virtio drivers. live-build produces a proper hybrid ISO with:

- `linux-image-amd64` + full firmware (`firmware-linux-nonfree`, `firmware-iwlwifi`, etc.)
- Real hardware drivers in initramfs (NVMe, SATA, AHCI, USB HID)
- `live-boot` for proper USB/CD detection
- SYSLINUX + GRUB EFI dual bootloaders (legacy BIOS and UEFI)

## Directory Structure

```
installer/
├── auto/
│   └── config              ← lb config arguments (Debian 13, amd64, iso-hybrid)
├── config/
│   ├── package-lists/
│   │   ├── hermit.list.chroot      ← packages in the live & target systems
│   │   └── hermit-live.list.binary ← live-boot packages
│   ├── hooks/
│   │   └── live/
│   │       ├── 0010-install-wizard-deps.hook.chroot  ← installs textual/rich
│   │       ├── 0020-configure-autologin.hook.chroot  ← autologin + .profile
│   │       └── 0030-networkmanager.hook.chroot        ← enables NetworkManager
│   └── includes.chroot/
│       └── opt/hermit-installer/wizard/  ← wizard source (copied by build.sh)
├── wizard/                 ← Python + Textual installer wizard (canonical source)
│   ├── main.py             ← entry point, HermitInstaller Textual App
│   └── screens/
│       ├── welcome.py      ← Step 1: intro & overview
│       ├── locale.py       ← Step 2: language & keyboard layout
│       ├── timezone.py     ← Step 3: timezone selection
│       ├── network.py      ← Step 4: ethernet/WiFi setup
│       ├── prime_name.py   ← Step 5: name your Prime agent
│       ├── drive.py        ← Step 6: drive selection (all block devices)
│       ├── drive_confirm.py← confirmation dialog before erase
│       ├── partition.py    ← Step 7: partitioning (EFI+root, +home, +swap)
│       ├── user_account.py ← Step 8: hostname, username, password
│       ├── base_install.py ← Step 9: debootstrap + base packages
│       ├── hermitos_stack.py ← Step 10: Hyprland, Incus, K3s, Hermetic, Ollama
│       ├── bootloader.py   ← Step 11: GRUB EFI + os-prober + initramfs
│       ├── nvidia.py       ← Optional: Nvidia driver detection & install
│       └── complete.py     ← Final: unmount & reboot
└── build.sh                ← Run this to build the ISO
```

## Build Requirements

- Debian 13 (Trixie) host (this is masternode)
- `live-build` package: `sudo apt install live-build`
- `debootstrap`: `sudo apt install debootstrap`
- Root access
- ~10GB free disk space for the build
- Internet access (downloads ~500MB from Debian mirrors)

## Building the ISO

```bash
cd ~/Code/HermitOS/installer
sudo ./build.sh
```

The build takes **20–40 minutes** on a fast connection. The output ISO will be named
`hermitos-installer-*.iso` in the installer directory.

## Writing to USB

```bash
# Find your USB drive (VERIFY THIS — don't overwrite your system disk!)
lsblk

# Write the ISO (replace /dev/sdX with your actual USB device)
sudo dd if=hermitos-installer-*.iso of=/dev/sdX bs=4M status=progress conv=fsync
sudo sync
```

> ⚠ **WARNING**: `dd` will silently overwrite anything at `/dev/sdX`. Triple-check the device path.

## Testing in QEMU (before writing to USB)

```bash
# BIOS boot test
qemu-system-x86_64 -m 2G -cdrom hermitos-installer-*.iso -boot d -enable-kvm

# UEFI boot test (install ovmf first: apt install ovmf)
qemu-system-x86_64 -m 2G -cdrom hermitos-installer-*.iso -boot d -enable-kvm \
    -bios /usr/share/ovmf/OVMF.fd
```

## Testing in Incus

```bash
# Create a VM with the ISO attached
incus launch images:debian/13/cloud testvm --vm -c limits.memory=2GiB
incus config device add testvm installer disk source=/path/to/hermitos-installer.iso boot.priority=10
incus restart testvm
incus console testvm
```

## Wizard Flow (12 steps + optional)

| Step | Screen | Description |
|------|--------|-------------|
| 1  | Welcome | Overview, hardware requirements |
| 2  | Language | Locale + keyboard layout |
| 3  | Timezone | System timezone |
| 4  | Network | Ethernet auto / WiFi scan+connect |
| 5  | Prime Name | Name your Hermetic Prime agent |
| 6  | Drive | Select target drive (all NVMe/SATA shown) |
| 7  | Partition | EFI+root, or +home, or +swap |
| 8  | User Account | Hostname, username, password |
| 9  | Base Install | `debootstrap` + kernel + firmware |
| 10 | HermitOS Stack | Hyprland, Incus, K3s, Hermetic, Ollama |
| 11 | Shore Register | Register prime tile in Shore dashboard |
| 12 | Bootloader | GRUB EFI + `os-prober` + `update-initramfs` |
| +  | Nvidia | Auto-detect; install proprietary driver if wanted |
| ✓  | Complete | Unmount + reboot |

## Shore Dynamic Prime Registration

Shore is the HermitOS SOC/watchdog dashboard. It displays a **tile grid** — one tile per
registered Hermetic prime running on the box.

### Registration Contract

The installer writes `/etc/hermetic/primes.d/<prime-name>.json`:

```json
{
  "name": "nova",
  "display": "Nova",
  "port": 7777,
  "dashboard_url": "http://localhost:7777",
  "health_url": "http://localhost:7777/status",
  "service": "nova.service",
  "shore_url": "http://localhost:7778",
  "registered_at": "2026-01-01T00:00:00Z",
  "installer_version": "1.0.0"
}
```

### Shore Tile Behavior

Shore reads all `.json` files in `/etc/hermetic/primes.d/` and renders one tile per entry.

Health polling (every 30s):
- `green`  — `GET health_url` returns HTTP 200
- `yellow` — non-200 or slow response (>3s)
- `red`    — connection refused / `systemctl is-active <service>` = inactive

Dynamic registration (at runtime):
- `POST http://localhost:7778/api/primes/register` with the same JSON schema
- New prime starts → sends registration → new tile appears instantly
- Prime stops → tile turns gray (Shore retries health checks for 60s then marks dead)

### Directory Watch (alternative)
Shore can also watch `/etc/hermetic/primes.d/` via inotify and pick up new files
without requiring a REST call. Both mechanisms are supported.

## What Gets Installed

**Base system:**
- Debian 13 (Trixie) via `debootstrap`
- `linux-image-amd64` with full firmware (`firmware-linux-nonfree`, WiFi, etc.)
- `initramfs` rebuilt with: nvme, ahci, sd_mod, xhci_hcd, usbhid
- NetworkManager, openssh-server, sudo, grub-efi-amd64

**HermitOS stack (selectable):**
- Hyprland (Wayland compositor) + Waybar + Wofi + Foot terminal
- Incus (LXC/LXD hypervisor)
- K3s (single-node Kubernetes)
- Hermetic (agent platform — your Prime runs here)
- Ollama (optional LLM runtime)
- uv + Go toolchain

## Troubleshooting

**Build fails with "debootstrap failed"**
- Check network connectivity
- Try a different Debian mirror: edit `auto/config` and change `--mirror-*` values

**ISO boots but kernel panics**
- Should not happen with live-build (proper initramfs with real hardware drivers)
- If it does: check `auto/config` for `--linux-flavours amd64`

**Wizard doesn't launch automatically**
- SSH into live system (user: `hermit-installer`, no password) or switch to tty2
- Run manually: `sudo python3 /opt/hermit-installer/wizard/main.py`

**Wifi adapter not detected**
- The live image includes: `firmware-iwlwifi`, `firmware-atheros`, `firmware-realtek`, `firmware-brcm80211`
- If your card needs different firmware, add it to `config/package-lists/hermit.list.chroot`
