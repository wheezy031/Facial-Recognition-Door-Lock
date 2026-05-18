# Using the Web UI

Open the UI in a browser:

```text
http://<raspberry-pi-ip>:8080/
```

The UI shows:

- Live camera stream.
- Camera worker status.
- Door lock state.
- Known people.
- Allow/deny controls.
- Merge tools.
- Manual lock/unlock control.

## Camera Status

The top toolbar shows whether the web service and camera worker are running.

The camera panel metadata shows:

```text
<backend> · stream <fps> fps · recognition <fps> fps
```

If the camera worker stops, the UI shows a camera fallback overlay even if the last stream image is still cached.

## People

When a new face is detected, the app creates a new identity. Each identity has:

- generated ID
- profile image
- allow/deny state
- sample count
- optional friendly name

Rename a person by editing the name field.

## Allow and Deny

Use the allowed/denied switch on each person.

- Allowed: recognised person can trigger the relay unlock.
- Denied: recognised person will not unlock the door.

## Add Sample

Use `Add sample` while the person is visible to capture another embedding for that identity.

Adding samples can improve matching for different lighting, angle, distance, or motion conditions.

## Merge People

Use merge when the same person has been detected as multiple identities.

1. Select two or more people.
2. The first selected person becomes the default merge target.
3. Choose another target if needed.
4. Click `Merge`.
5. Confirm the selected source identities.

The target identity is kept. Source identities are removed after their samples are merged into the target.

## Manual Door Control

The toolbar includes a manual door action button.

- If the door state is locked, the button shows `Unlock`.
- If the door state is unlocked, the button shows `Lock now`.

The UI state reflects the software-controlled relay state. It does not confirm physical latch position unless you add a separate lock sensor.

## Mock Mode

Mock mode is useful for testing without a camera.

The UI shows a notice when mock mode is active.

```bash
sudo sed -i 's/^DOORLOCK_CAMERA_BACKEND=.*/DOORLOCK_CAMERA_BACKEND="mock"/' /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```
