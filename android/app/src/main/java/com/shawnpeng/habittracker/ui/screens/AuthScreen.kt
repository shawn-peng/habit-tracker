package com.shawnpeng.habittracker.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Cloud
import androidx.compose.material.icons.rounded.Email
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.DEFAULT_EMULATOR_URL

@Composable
fun AuthScreen(
    initialServerUrl: String,
    isSubmitting: Boolean,
    errorMessage: String?,
    infoMessage: String? = null,
    pendingVerificationEmail: String? = null,
    resetCodeSentEmail: String? = null,
    onLogin: (serverUrl: String, email: String, password: String) -> Unit,
    onRegister: (serverUrl: String, name: String, email: String, password: String) -> Unit,
    onVerifyEmail: (serverUrl: String, email: String, code: String) -> Unit = { _, _, _ -> },
    onResendVerification: (serverUrl: String, email: String) -> Unit = { _, _ -> },
    onClearFeedback: () -> Unit = {},
    onRequestPasswordReset: (serverUrl: String, email: String) -> Unit = { _, _ -> },
    onConfirmPasswordReset: (
        serverUrl: String,
        email: String,
        code: String,
        newPassword: String,
        confirmPassword: String,
    ) -> Unit = { _, _, _, _, _ -> },
) {
    var isRegister by remember { mutableStateOf(false) }
    var isVerifyEmail by remember { mutableStateOf(false) }
    var isForgotPassword by remember { mutableStateOf(false) }
    var hasResetCode by remember { mutableStateOf(false) }
    var serverUrl by remember(initialServerUrl) { mutableStateOf(initialServerUrl) }
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var passwordVisible by remember { mutableStateOf(false) }
    var verificationCode by remember { mutableStateOf("") }
    var resetCode by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var newPasswordVisible by remember { mutableStateOf(false) }
    val focusManager = LocalFocusManager.current
    val submitAuth: () -> Unit = {
        if (!isSubmitting) {
            focusManager.clearFocus()
            when {
                isVerifyEmail -> onVerifyEmail(serverUrl, email, verificationCode)
                isForgotPassword && !hasResetCode -> onRequestPasswordReset(serverUrl, email)
                isForgotPassword -> onConfirmPasswordReset(
                    serverUrl,
                    email,
                    resetCode,
                    newPassword,
                    confirmPassword,
                )
                isRegister -> onRegister(serverUrl, name, email, password)
                else -> onLogin(serverUrl, email, password)
            }
        }
    }

    LaunchedEffect(pendingVerificationEmail) {
        if (!pendingVerificationEmail.isNullOrBlank()) {
            email = pendingVerificationEmail
            isVerifyEmail = true
            isForgotPassword = false
            hasResetCode = false
            verificationCode = ""
        }
    }

    LaunchedEffect(resetCodeSentEmail) {
        if (!resetCodeSentEmail.isNullOrBlank()) {
            hasResetCode = true
        }
    }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(horizontal = 20.dp, vertical = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .widthIn(max = 440.dp),
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.Verified,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(32.dp),
                        )
                        Text(
                            text = "Habit Tracker",
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold,
                        )
                    }

                    Text(
                        text = when {
                            isVerifyEmail -> "Enter the 6-digit verification code sent to your email to activate your account"
                            isForgotPassword -> "Enter your registered email to receive a 6-digit password reset code"
                            else -> "Connect to the FastAPI + MongoDB backend to sync your daily habits & streaks"
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                    )

                    if (isVerifyEmail) {
                        Text(
                            text = "Verify Email",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                    } else if (isForgotPassword) {
                        Text(
                            text = "Reset Password",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                    } else {
                        TabRow(selectedTabIndex = if (isRegister) 1 else 0) {
                            Tab(
                                selected = !isRegister,
                                onClick = {
                                    isRegister = false
                                    onClearFeedback()
                                },
                                text = { Text("Sign In") },
                            )
                            Tab(
                                selected = isRegister,
                                onClick = {
                                    isRegister = true
                                    onClearFeedback()
                                },
                                text = { Text("Create Account") },
                            )
                        }
                    }

                    OutlinedTextField(
                        value = serverUrl,
                        onValueChange = { serverUrl = it },
                        label = { Text("Server API URL") },
                        placeholder = { Text(DEFAULT_EMULATOR_URL) },
                        leadingIcon = { Icon(Icons.Rounded.Cloud, contentDescription = null) },
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Uri,
                            imeAction = ImeAction.Next,
                        ),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )

                    Column(
                        modifier = Modifier.fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            AssistChip(
                                onClick = { serverUrl = DEFAULT_EMULATOR_URL },
                                label = { Text("Emulator 10.0.2.2") },
                            )
                            AssistChip(
                                onClick = { serverUrl = "http://192.168.1.50:8000" },
                                label = { Text("LAN Example") },
                            )
                        }
                        Text(
                            text = "Use http://10.0.2.2:8000 in the Android Emulator, or your computer's LAN IP (e.g. http://192.168.x.x:8000) on a physical device.",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    if (!isForgotPassword && !isVerifyEmail && isRegister) {
                        OutlinedTextField(
                            value = name,
                            onValueChange = { name = it },
                            label = { Text("Full Name") },
                            leadingIcon = { Icon(Icons.Rounded.Person, contentDescription = null) },
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }

                    OutlinedTextField(
                        value = email,
                        onValueChange = { email = it },
                        label = { Text("Email") },
                        leadingIcon = { Icon(Icons.Rounded.Email, contentDescription = null) },
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Email,
                            imeAction = if (isForgotPassword && !hasResetCode) {
                                ImeAction.Done
                            } else {
                                ImeAction.Next
                            },
                        ),
                        keyboardActions = KeyboardActions(
                            onDone = { submitAuth() },
                        ),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )

                    if (!isForgotPassword && !isVerifyEmail) {
                        OutlinedTextField(
                            value = password,
                            onValueChange = { password = it },
                            label = { Text("Password") },
                            leadingIcon = { Icon(Icons.Rounded.Lock, contentDescription = null) },
                            trailingIcon = {
                                IconButton(onClick = { passwordVisible = !passwordVisible }) {
                                    Icon(
                                        imageVector = if (passwordVisible) Icons.Rounded.VisibilityOff
                                        else Icons.Rounded.Visibility,
                                        contentDescription = if (passwordVisible) "Hide password" else "Show password",
                                    )
                                }
                            },
                            visualTransformation = if (passwordVisible) {
                                VisualTransformation.None
                            } else {
                                PasswordVisualTransformation()
                            },
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Password,
                                imeAction = ImeAction.Done,
                            ),
                            keyboardActions = KeyboardActions(
                                onDone = { submitAuth() },
                            ),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )

                        if (!isRegister) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.End,
                            ) {
                                TextButton(
                                    onClick = {
                                        isForgotPassword = true
                                        isVerifyEmail = false
                                        hasResetCode = false
                                        resetCode = ""
                                        newPassword = ""
                                        confirmPassword = ""
                                        onClearFeedback()
                                    },
                                ) {
                                    Text("Forgot password?")
                                }
                            }
                        }
                    } else if (isVerifyEmail) {
                        NumericCodeField(
                            value = verificationCode,
                            onValueChange = { verificationCode = it },
                            imeAction = ImeAction.Done,
                            onDone = submitAuth,
                        )
                    } else if (hasResetCode) {
                        NumericCodeField(
                            value = resetCode,
                            onValueChange = { resetCode = it },
                            imeAction = ImeAction.Next,
                        )

                        OutlinedTextField(
                            value = newPassword,
                            onValueChange = { newPassword = it },
                            label = { Text("New Password (at least 6 chars)") },
                            leadingIcon = { Icon(Icons.Rounded.Lock, contentDescription = null) },
                            trailingIcon = {
                                IconButton(onClick = { newPasswordVisible = !newPasswordVisible }) {
                                    Icon(
                                        imageVector = if (newPasswordVisible) Icons.Rounded.VisibilityOff
                                        else Icons.Rounded.Visibility,
                                        contentDescription = if (newPasswordVisible) "Hide password" else "Show password",
                                    )
                                }
                            },
                            visualTransformation = if (newPasswordVisible) {
                                VisualTransformation.None
                            } else {
                                PasswordVisualTransformation()
                            },
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Password,
                                imeAction = ImeAction.Next,
                            ),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )

                        OutlinedTextField(
                            value = confirmPassword,
                            onValueChange = { confirmPassword = it },
                            label = { Text("Confirm New Password") },
                            leadingIcon = { Icon(Icons.Rounded.Lock, contentDescription = null) },
                            trailingIcon = {
                                IconButton(onClick = { newPasswordVisible = !newPasswordVisible }) {
                                    Icon(
                                        imageVector = if (newPasswordVisible) Icons.Rounded.VisibilityOff
                                        else Icons.Rounded.Visibility,
                                        contentDescription = if (newPasswordVisible) "Hide password" else "Show password",
                                    )
                                }
                            },
                            visualTransformation = if (newPasswordVisible) {
                                VisualTransformation.None
                            } else {
                                PasswordVisualTransformation()
                            },
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Password,
                                imeAction = ImeAction.Done,
                            ),
                            keyboardActions = KeyboardActions(
                                onDone = { submitAuth() },
                            ),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }

                    if (!infoMessage.isNullOrBlank()) {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp),
                            color = MaterialTheme.colorScheme.primaryContainer,
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Icon(
                                    imageVector = Icons.Rounded.Check,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                                    modifier = Modifier.size(18.dp),
                                )
                                Text(
                                    text = infoMessage,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                                )
                            }
                        }
                    }

                    if (!errorMessage.isNullOrBlank()) {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp),
                            color = MaterialTheme.colorScheme.errorContainer,
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Icon(
                                    imageVector = Icons.Rounded.ErrorOutline,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.onErrorContainer,
                                    modifier = Modifier.size(18.dp),
                                )
                                Text(
                                    text = errorMessage,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onErrorContainer,
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(2.dp))

                    Button(
                        onClick = submitAuth,
                        enabled = !isSubmitting,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp),
                        shape = RoundedCornerShape(12.dp),
                    ) {
                        if (isSubmitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp,
                                color = MaterialTheme.colorScheme.onPrimary,
                            )
                        } else {
                            Text(
                                text = when {
                                    isVerifyEmail -> "Verify Email & Sign In"
                                    isForgotPassword && !hasResetCode -> "Send 6-Digit Code"
                                    isForgotPassword -> "Reset Password & Sign In"
                                    isRegister -> "Create Account"
                                    else -> "Sign In"
                                },
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                    }

                    if (isVerifyEmail) {
                        TextButton(
                            onClick = {
                                focusManager.clearFocus()
                                onResendVerification(serverUrl, email)
                            },
                            enabled = !isSubmitting,
                        ) {
                            Text("Resend Code")
                        }

                        TextButton(
                            onClick = {
                                isVerifyEmail = false
                                isForgotPassword = false
                                isRegister = false
                                verificationCode = ""
                                onClearFeedback()
                            },
                            enabled = !isSubmitting,
                        ) {
                            Text("Back to Sign In")
                        }
                    } else if (isForgotPassword) {
                        if (!hasResetCode) {
                            TextButton(
                                onClick = {
                                    onClearFeedback()
                                    hasResetCode = true
                                },
                                enabled = !isSubmitting,
                            ) {
                                Text("Already have a code? Enter it")
                            }
                        } else {
                            TextButton(
                                onClick = { onRequestPasswordReset(serverUrl, email) },
                                enabled = !isSubmitting,
                            ) {
                                Text("Resend Code")
                            }
                        }

                        TextButton(
                            onClick = {
                                isForgotPassword = false
                                hasResetCode = false
                                onClearFeedback()
                            },
                            enabled = !isSubmitting,
                        ) {
                            Text("Back to Sign In")
                        }
                    } else if (isRegister) {
                        TextButton(
                            onClick = {
                                isVerifyEmail = true
                                isForgotPassword = false
                                verificationCode = ""
                                onClearFeedback()
                            },
                            enabled = !isSubmitting,
                        ) {
                            Text("Already have a code? Verify Email")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun NumericCodeField(
    value: String,
    onValueChange: (String) -> Unit,
    imeAction: ImeAction,
    onDone: (() -> Unit)? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = { raw ->
            val digitsOnly = raw.filter(Char::isDigit)
            if (digitsOnly.length <= 6) {
                onValueChange(digitsOnly)
            }
        },
        label = { Text("6-Digit Verification Code") },
        leadingIcon = { Icon(Icons.Rounded.Verified, contentDescription = null) },
        keyboardOptions = KeyboardOptions(
            keyboardType = KeyboardType.Number,
            imeAction = imeAction,
        ),
        keyboardActions = if (onDone != null) {
            KeyboardActions(onDone = { onDone() })
        } else {
            KeyboardActions.Default
        },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}
